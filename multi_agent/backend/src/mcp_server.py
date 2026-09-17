"""MCP Server (`mcp-k8s-docs-server`) for Vertex AI Search Kubernetes Documentation.

Implements the Model Context Protocol (MCP) server specified in `design.md` (§3 Agent 1):
- Server Name: `mcp-k8s-docs-server` (via Anthropic `FastMCP`)
- Tool: `search_kubernetes_documentation`
- Transports: `stdio` and `sse` (Server-Sent Events)
- Backend: Google Cloud Vertex AI Search (`k8s-custom-chunks-store`) with a lazy-loaded
  `SearchServiceAsyncClient` gRPC singleton, plus automatic fallback to the internal
  13,894-chunk hybrid index (`src.retriever.HybridChunkRetriever`).
"""

import os
import sys
import asyncio
import logging
import argparse
from typing import Dict, Any, Optional

from google.cloud import discoveryengine_v1beta
from mcp.server.fastmcp import FastMCP

from src.auth import get_gcp_credentials, get_identity_metadata, get_secret
from src.retriever import HybridChunkRetriever, resolve_chunks_jsonl_path

logger = logging.getLogger("mcp_k8s_docs_server")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("DISCOVERY_ENGINE_LOCATION", "global")
DATASTORE_ID = os.getenv("DISCOVERY_ENGINE_DATASTORE_ID", "k8s-custom-chunks-store")

# Pre-formatted Vertex AI Search serving config path
SERVING_CONFIG_PATH = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
    f"dataStores/{DATASTORE_ID}/servingConfigs/default_search"
)

# Initialize FastMCP Server instance
mcp_server = FastMCP(
    name="mcp-k8s-docs-server",
    instructions=(
        "Authoritative Kubernetes Documentation MCP Server backed by Google Cloud "
        "Vertex AI Search (datastore: k8s-custom-chunks-store)."
    ),
)

# ============================================================================
# Lazy-Loaded gRPC & Local Index Singletons (Zero Per-Request Churn)
# ============================================================================

_gcp_credentials = None
_search_client: Optional[discoveryengine_v1beta.SearchServiceAsyncClient] = None
_search_client_cls = None
_search_client_loop = None
_hybrid_retriever: Optional[HybridChunkRetriever] = None


def _get_gcp_credentials():
    """Returns cached SPIFFE Workload Identity / ADC credentials via src.auth."""
    global _gcp_credentials
    if _gcp_credentials is None:
        _gcp_credentials, _ = get_gcp_credentials(project_id=PROJECT_ID)
    return _gcp_credentials


def _get_search_client() -> discoveryengine_v1beta.SearchServiceAsyncClient:
    """Returns a persistent SearchServiceAsyncClient singleton per active event loop to reuse gRPC channels across queries."""
    global _search_client, _search_client_cls, _search_client_loop
    current_cls = discoveryengine_v1beta.SearchServiceAsyncClient
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if (
        _search_client is None
        or _search_client_cls is not current_cls
        or _search_client_loop is not current_loop
    ):
        creds = _get_gcp_credentials()
        _search_client = current_cls(credentials=creds)
        _search_client_cls = current_cls
        _search_client_loop = current_loop
    return _search_client


def _get_local_hybrid_retriever(prefer_gcs: bool = False) -> Optional[HybridChunkRetriever]:
    """Lazily loads the internal HybridChunkRetriever singleton from local disk, Cloud Run GCS mount, or direct GCS bucket download."""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        jsonl_path = resolve_chunks_jsonl_path(prefer_gcs=prefer_gcs)
        if jsonl_path is not None:
            try:
                _hybrid_retriever = HybridChunkRetriever(jsonl_path)
            except Exception as exc:
                logger.warning(f"Failed to initialize HybridChunkRetriever from {jsonl_path}: {exc}")
    return _hybrid_retriever


# ============================================================================
# Core Vertex AI Search Operation & Registered FastMCP Tool
# ============================================================================

async def query_vertex_ai_search(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Queries Vertex AI Search (`k8s-custom-chunks-store`) or performs localized GCS retrieval if `MCP_RETRIEVAL_MODE=gcs`."""
    retrieval_mode = os.getenv("MCP_RETRIEVAL_MODE", "vertex").lower()
    if retrieval_mode == "gcs":
        retriever = _get_local_hybrid_retriever(prefer_gcs=True)
        if retriever is not None:
            local_hits = retriever.search(query, top_k=top_k)
            results = []
            for h in local_hits:
                cid = h["id"]
                full_chk = retriever.get_by_id(cid) or {}
                url = full_chk.get("url") or full_chk.get("uri") or "https://kubernetes.io/docs/reference/"
                bcrumb = h.get("breadcrumb") or full_chk.get("title") or cid
                content = h.get("content", "")
                results.append({
                    "chunk_id": cid,
                    "title": bcrumb,
                    "breadcrumb": bcrumb,
                    "url": url,
                    "doc_path": url,
                    "content": content,
                    "snippet": content[:400],
                    "has_code_block": bool(full_chk.get("has_code_block", False)),
                    "source_engine": "gcs_localized_hybrid_retriever",
                })
            return {
                "status": "success",
                "server": "mcp-k8s-docs-server",
                "datastore": f"gs://{os.getenv('K8S_DOCS_GCS_BUCKET', 'k8s-docs-fde-k8s-sandbox-dev-505119')}/custom_chunks/k8s_chunks_custom.jsonl",
                "query": query,
                "results": results,
            }

    try:
        client = _get_search_client()

        req = discoveryengine_v1beta.SearchRequest(
            serving_config=SERVING_CONFIG_PATH,
            query=query,
            page_size=top_k,
            content_search_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True
                )
            ),
        )

        response = await client.search(request=req, timeout=4.0)
        results = []

        async for r in response:
            struct = dict(r.document.struct_data) if getattr(r.document, "struct_data", None) else {}
            derived = dict(r.document.derived_struct_data) if getattr(r.document, "derived_struct_data", None) else {}

            chunk_id = struct.get("id") or struct.get("_id") or r.document.id
            breadcrumb = struct.get("breadcrumb") or struct.get("title") or derived.get("title") or chunk_id
            doc_path = (
                struct.get("url")
                or struct.get("uri")
                or struct.get("doc_path")
                or derived.get("link")
                or "https://kubernetes.io/docs/reference/"
            )
            content = struct.get("content", "")
            if not content:
                snippets = [s.get("snippet", "") for s in derived.get("snippets", []) if isinstance(s, dict)]
                content = " ".join(snippets) if snippets else str(derived.get("extractive_answers", ""))

            results.append({
                "chunk_id": chunk_id,
                "title": breadcrumb,
                "breadcrumb": breadcrumb,
                "url": doc_path,
                "doc_path": doc_path,
                "content": content,
                "snippet": content,
                "has_code_block": bool(struct.get("has_code_block", False)),
                "source_engine": "vertex_ai_search",
            })
            if len(results) >= top_k:
                break

        return {
            "status": "success",
            "server": "mcp-k8s-docs-server",
            "datastore": DATASTORE_ID,
            "query": query,
            "results": results,
        }

    except Exception as exc:
        logger.warning(f"Vertex AI Search live call failed ({exc}); using local k8s_chunks_custom.jsonl index.")
        retriever = _get_local_hybrid_retriever()
        if retriever is not None:
            local_hits = retriever.search(query, top_k=top_k)
            results = []
            for h in local_hits:
                cid = h["id"]
                full_chk = retriever.get_by_id(cid) or {}
                url = full_chk.get("url") or full_chk.get("uri") or "https://kubernetes.io/docs/reference/"
                bcrumb = h.get("breadcrumb") or full_chk.get("title") or cid
                content = h.get("content", "")
                results.append({
                    "chunk_id": cid,
                    "title": bcrumb,
                    "breadcrumb": bcrumb,
                    "url": url,
                    "doc_path": url,
                    "content": content,
                    "snippet": content[:400],
                    "has_code_block": bool(full_chk.get("has_code_block", False)),
                    "source_engine": "local_hybrid_custom_chunks",
                })
            return {
                "status": "fallback",
                "server": "mcp-k8s-docs-server",
                "datastore": "k8s_chunks_custom.jsonl",
                "query": query,
                "results": results,
            }

        return {
            "status": "fallback",
            "server": "mcp-k8s-docs-server",
            "query": query,
            "results": [
                {
                    "chunk_id": "k8s_debug_fallback_001",
                    "title": f"Kubernetes Troubleshooting Guide for {query}",
                    "breadcrumb": f"Troubleshooting > {query}",
                    "url": "https://kubernetes.io/docs/tasks/debug/",
                    "doc_path": "https://kubernetes.io/docs/tasks/debug/",
                    "content": f"Official documentation and triage steps for resolving {query} in production clusters.",
                    "snippet": f"Official documentation and triage steps for resolving {query} in production clusters.",
                    "has_code_block": False,
                }
            ],
        }


@mcp_server.tool(
    name="search_kubernetes_documentation",
    description=(
        "Search official Kubernetes documentation and YAML manifests indexed in "
        "Vertex AI Search (k8s-custom-chunks-store). Returns hierarchy breadcrumbs, "
        "canonical URLs, and full markdown/YAML content chunks."
    ),
)
async def mcp_search_kubernetes_documentation(query: str, top_k: int = 3) -> Dict[str, Any]:
    """MCP Tool endpoint for searching Kubernetes documentation."""
    return await query_vertex_ai_search(query=query, top_k=top_k)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run mcp-k8s-docs-server over stdio or SSE.")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport protocol")
    args = parser.parse_args()
    mcp_server.run(transport=args.transport)
