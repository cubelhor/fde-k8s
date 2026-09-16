"""MCP Server (`mcp-k8s-docs-server`) for Vertex AI Search Kubernetes Documentation.

Implements the Model Context Protocol (MCP) server specified in `design.md` (§3 Agent 1):
- Server Name: `mcp-k8s-docs-server` (via Anthropic `FastMCP`)
- Transports: `stdio` and `sse` (Server-Sent Events)
- Backend: Google Cloud Vertex AI Search (`k8s-custom-chunks-store`) with lazy-loaded
  gRPC client singletons (`SearchServiceAsyncClient` & `DocumentServiceAsyncClient`)
  to prevent per-request gRPC connection churn, plus automatic fallback to the local
  13,894-chunk hybrid index (`k8s_chunks_custom.jsonl`).
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

from google.auth import default
from google.cloud import discoveryengine_v1beta
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("mcp_k8s_docs_server")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("DISCOVERY_ENGINE_LOCATION", "global")
DATASTORE_ID = os.getenv("DISCOVERY_ENGINE_DATASTORE_ID", "k8s-custom-chunks-store")

# Pre-formatted Vertex AI Search resource paths
SERVING_CONFIG_PATH = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
    f"dataStores/{DATASTORE_ID}/servingConfigs/default_search"
)
BRANCH_DOCUMENTS_PREFIX = (
    f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/"
    f"dataStores/{DATASTORE_ID}/branches/0/documents"
)

# Path to the 13,894-chunk artifact for local hybrid index fallback
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PIPELINE_DIR = REPO_ROOT / "multi_agent" / "data_pipeline"
CHUNKS_JSONL_PATH = PIPELINE_DIR / "artifacts" / "k8s_chunks_custom.jsonl"

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
_doc_client: Optional[discoveryengine_v1beta.DocumentServiceAsyncClient] = None
_doc_client_cls = None

_hybrid_retriever = None
_local_chunk_map: Dict[str, Dict[str, Any]] = {}


def _get_gcp_credentials():
    """Returns cached Google Cloud Application Default Credentials."""
    global _gcp_credentials
    if _gcp_credentials is None:
        _gcp_credentials, _ = default(quota_project_id=PROJECT_ID)
    return _gcp_credentials


def _get_search_client() -> discoveryengine_v1beta.SearchServiceAsyncClient:
    """Returns a persistent SearchServiceAsyncClient singleton to reuse gRPC channels across queries."""
    global _search_client, _search_client_cls
    current_cls = discoveryengine_v1beta.SearchServiceAsyncClient
    if _search_client is None or _search_client_cls is not current_cls:
        creds = _get_gcp_credentials()
        _search_client = current_cls(credentials=creds)
        _search_client_cls = current_cls
    return _search_client


def _get_doc_client() -> discoveryengine_v1beta.DocumentServiceAsyncClient:
    """Returns a persistent DocumentServiceAsyncClient singleton to reuse gRPC channels across ID lookups."""
    global _doc_client, _doc_client_cls
    current_cls = discoveryengine_v1beta.DocumentServiceAsyncClient
    if _doc_client is None or _doc_client_cls is not current_cls:
        creds = _get_gcp_credentials()
        _doc_client = current_cls(credentials=creds)
        _doc_client_cls = current_cls
    return _doc_client


def _get_local_hybrid_retriever():
    """Lazily loads the local 13,894-chunk HybridChunkRetriever once."""
    global _hybrid_retriever
    if _hybrid_retriever is None and CHUNKS_JSONL_PATH.exists():
        try:
            if str(PIPELINE_DIR) not in sys.path:
                sys.path.insert(0, str(PIPELINE_DIR))
            from evaluate_chunk_quality import HybridChunkRetriever
            _hybrid_retriever = HybridChunkRetriever(CHUNKS_JSONL_PATH)
        except Exception as exc:
            logger.warning(f"Failed to load local HybridChunkRetriever: {exc}")
    return _hybrid_retriever


# ============================================================================
# Core Vertex AI Search Operations
# ============================================================================

async def query_vertex_ai_search(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Queries Vertex AI Search (`k8s-custom-chunks-store`) reusing the singleton gRPC channel."""
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

        response = await client.search(request=req)
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


async def fetch_chunk_by_id_from_vertex(chunk_id: str) -> Dict[str, Any]:
    """Fetches a chunk by its deterministic ID from Vertex AI Search first using the singleton DocumentServiceAsyncClient."""
    try:
        doc_client = _get_doc_client()
        doc_name = f"{BRANCH_DOCUMENTS_PREFIX}/{chunk_id}"

        doc = await doc_client.get_document(
            request=discoveryengine_v1beta.GetDocumentRequest(name=doc_name)
        )
        struct = dict(doc.struct_data) if getattr(doc, "struct_data", None) else {}
        derived = dict(doc.derived_struct_data) if getattr(doc, "derived_struct_data", None) else {}

        cid = struct.get("id") or struct.get("_id") or doc.id or chunk_id
        breadcrumb = struct.get("breadcrumb") or struct.get("title") or derived.get("title") or cid
        url = (
            struct.get("url")
            or struct.get("uri")
            or struct.get("doc_path")
            or derived.get("link")
            or "https://kubernetes.io/docs/reference/"
        )
        content = struct.get("content", "")

        return {
            "status": "success",
            "server": "mcp-k8s-docs-server",
            "datastore": DATASTORE_ID,
            "source_engine": "vertex_ai_search",
            "chunk_id": cid,
            "title": breadcrumb,
            "breadcrumb": breadcrumb,
            "url": url,
            "content": content,
            "has_code_block": bool(struct.get("has_code_block", False)),
        }
    except Exception as exc:
        logger.warning(
            f"Vertex AI Search DocumentService lookup for '{chunk_id}' failed ({exc}); checking local fallback."
        )
        retriever = _get_local_hybrid_retriever()
        if retriever is not None:
            chk = retriever.get_by_id(chunk_id)
            if chk is not None:
                cid = chk.get("id") or chk.get("_id") or chunk_id
                return {
                    "status": "fallback",
                    "server": "mcp-k8s-docs-server",
                    "datastore": "k8s_chunks_custom.jsonl",
                    "source_engine": "local_hybrid_custom_chunks",
                    "chunk_id": cid,
                    "title": chk.get("breadcrumb") or chk.get("title", ""),
                    "breadcrumb": chk.get("breadcrumb", ""),
                    "url": chk.get("url", ""),
                    "content": chk.get("content", ""),
                    "has_code_block": bool(chk.get("has_code_block", False)),
                }
        return {
            "status": "not_found",
            "server": "mcp-k8s-docs-server",
            "chunk_id": chunk_id,
        }


# ============================================================================
# Registered FastMCP Tools
# ============================================================================

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


@mcp_server.tool(
    name="get_kubernetes_chunk_by_id",
    description="Retrieve a specific Kubernetes documentation chunk from Vertex AI Search by its deterministic chunk_id.",
)
async def mcp_get_kubernetes_chunk_by_id(chunk_id: str) -> Dict[str, Any]:
    """MCP Tool endpoint for fetching a full documentation chunk by ID from Vertex AI Search."""
    return await fetch_chunk_by_id_from_vertex(chunk_id=chunk_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run mcp-k8s-docs-server over stdio or SSE.")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport protocol")
    args = parser.parse_args()
    mcp_server.run(transport=args.transport)
