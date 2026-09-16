"""Async Tools for the Kubernetes Troubleshooting Copilot.

Integrates the MCP Server (`mcp-k8s-docs-server`) and Vertex AI Search
(`k8s-custom-chunks-store`) for authoritative documentation retrieval.
"""

import os
import logging
from typing import Dict, Any, List

from google.cloud import discoveryengine_v1beta
from google.auth import default

from src.mcp_server import mcp_server, _get_local_hybrid_retriever

logger = logging.getLogger("k8s_tools")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
DATASTORE_ID = os.getenv("DISCOVERY_ENGINE_DATASTORE_ID", "k8s-custom-chunks-store")

# Tracks the most recent documentation chunks retrieved via MCP / Vertex AI Search
_recent_retrieved_chunks: List[Dict[str, Any]] = []


def get_and_clear_recent_chunks() -> List[Dict[str, Any]]:
    """Returns and resets the buffer of chunks retrieved during the current agent turn."""
    global _recent_retrieved_chunks
    items = list(_recent_retrieved_chunks)
    _recent_retrieved_chunks.clear()
    return items


async def search_kubernetes_documentation(query: str) -> Dict[str, Any]:
    """Search official Kubernetes reference documentation via `mcp-k8s-docs-server` (Vertex AI Search).

    Args:
        query: Specific technical query or error keyword (e.g. 'CrashLoopBackOff', 'OOMKilled', 'CoreDNS').

    Returns:
        A dictionary containing relevant documentation snippets, titles, breadcrumbs, and source URLs.
    """
    global _recent_retrieved_chunks
    try:
        creds, _ = default(quota_project_id=PROJECT_ID)
        client = discoveryengine_v1beta.SearchServiceAsyncClient(credentials=creds)
        serving_config = (
            f"projects/{PROJECT_ID}/locations/global/collections/default_collection/"
            f"dataStores/{DATASTORE_ID}/servingConfigs/default_search"
        )

        req = discoveryengine_v1beta.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=3,
            content_search_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec(
                snippet_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True
                )
            ),
        )

        response = await client.search(request=req)
        results = []

        # Async iterator across SearchResponse results
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

            chunk_entry = {
                "chunk_id": chunk_id,
                "title": breadcrumb,
                "breadcrumb": breadcrumb,
                "url": doc_path,
                "doc_path": doc_path,
                "content": content,
                "snippet": content,
                "has_code_block": bool(struct.get("has_code_block", False)),
                "mcp_server": mcp_server.name,
            }
            results.append(chunk_entry)
            _recent_retrieved_chunks.append(chunk_entry)

        return {
            "status": "success",
            "mcp_server": mcp_server.name,
            "datastore": DATASTORE_ID,
            "query": query,
            "results": results,
        }
    except Exception as exc:
        logger.warning(f"Discovery Engine search fallback (Offline/Mock): {exc}")
        retriever = _get_local_hybrid_retriever()
        if retriever is not None:
            local_hits = retriever.search(query, top_k=3)
            chunk_map = {c.get("id", c.get("_id", "")): c for c in retriever.chunks}
            results = []
            for h in local_hits:
                cid = h["id"]
                full_chk = chunk_map.get(cid, {})
                url = full_chk.get("url") or full_chk.get("uri") or "https://kubernetes.io/docs/tasks/debug/"
                bcrumb = h.get("breadcrumb") or full_chk.get("title") or f"Kubernetes Troubleshooting Guide for {query}"
                content = h.get("content", "")
                entry = {
                    "chunk_id": cid,
                    "title": bcrumb,
                    "breadcrumb": bcrumb,
                    "url": url,
                    "doc_path": url,
                    "content": content,
                    "snippet": content[:400],
                    "has_code_block": bool(full_chk.get("has_code_block", False)),
                    "mcp_server": mcp_server.name,
                }
                results.append(entry)
                _recent_retrieved_chunks.append(entry)
            if results:
                return {
                    "status": "fallback",
                    "mcp_server": mcp_server.name,
                    "datastore": "k8s_chunks_custom.jsonl",
                    "query": query,
                    "results": results,
                }

        fallback_entry = {
            "chunk_id": "k8s_debug_fallback_001",
            "title": f"Kubernetes Troubleshooting Guide for {query}",
            "breadcrumb": f"Kubernetes Troubleshooting Guide for {query}",
            "url": "https://kubernetes.io/docs/tasks/debug/",
            "doc_path": "https://kubernetes.io/docs/tasks/debug/",
            "content": f"Official documentation and triage steps for resolving {query} in production clusters.",
            "snippet": f"Official documentation and triage steps for resolving {query} in production clusters.",
            "has_code_block": False,
            "mcp_server": mcp_server.name,
        }
        _recent_retrieved_chunks.append(fallback_entry)
        return {
            "status": "fallback",
            "mcp_server": mcp_server.name,
            "query": query,
            "results": [fallback_entry],
        }
