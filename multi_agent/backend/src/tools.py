"""Async Tools for the Kubernetes Troubleshooting Copilot.

Integrates the MCP Server (`mcp-k8s-docs-server`) and Vertex AI Search
(`k8s-custom-chunks-store`) for authoritative documentation retrieval
using persistent gRPC client singletons.
"""

from typing import Dict, Any, List

from src.mcp_server import (
    mcp_server,
    mcp_search_kubernetes_documentation,
    DATASTORE_ID,
)

# Tracks the most recent documentation chunks retrieved via MCP / Vertex AI Search
_recent_retrieved_chunks: List[Dict[str, Any]] = []


def get_and_clear_recent_chunks() -> List[Dict[str, Any]]:
    """Returns and resets the buffer of chunks retrieved during the current agent turn."""
    global _recent_retrieved_chunks
    items = list(_recent_retrieved_chunks)
    _recent_retrieved_chunks.clear()
    return items


async def search_kubernetes_documentation(query: str) -> Dict[str, Any]:
    """Search official Kubernetes reference documentation via `mcp-k8s-docs-server` (`search_kubernetes_documentation`).

    Args:
        query: Specific technical query or error keyword (e.g. 'CrashLoopBackOff', 'OOMKilled', 'CoreDNS').

    Returns:
        A dictionary containing relevant documentation snippets, titles, breadcrumbs, and source URLs.
    """
    global _recent_retrieved_chunks
    mcp_response = await mcp_search_kubernetes_documentation(query=query, top_k=3)
    results = []
    for chunk in mcp_response.get("results", []):
        entry = dict(chunk)
        entry.setdefault("mcp_server", mcp_server.name)
        results.append(entry)
        _recent_retrieved_chunks.append(entry)

    return {
        "status": mcp_response.get("status", "success"),
        "mcp_server": mcp_server.name,
        "datastore": mcp_response.get("datastore", DATASTORE_ID),
        "query": query,
        "results": results,
    }

