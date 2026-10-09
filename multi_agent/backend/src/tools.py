"""Async Tools for the Kubernetes Troubleshooting Copilot.

Integrates the MCP Server (`mcp-k8s-docs-server`) and Vertex AI Search
(`k8s-custom-chunks-store`) for authoritative documentation retrieval
using ADK's native `ToolContext.state`.
"""

from typing import Dict, Any, Optional
import httpx
from google.adk.tools import ToolContext

from src.auth import fetch_agent_id_token
from src.config import DEFAULT_SPIFFE_ID
import src.config as config_mod
from src.mcp_server import (
    mcp_server,
    mcp_search_kubernetes_documentation,
    DATASTORE_ID,
)


async def _call_remote_mcp_microservice(mcp_url: str, query: str, top_k: int = 3) -> Dict[str, Any]:
    """Invokes the standalone `mcp-k8s-docs-server` microservice using the Agent's OIDC/SPIFFE identity."""
    headers = {"X-Agent-Spiffe-Id": DEFAULT_SPIFFE_ID}
    token = fetch_agent_id_token(target_audience=mcp_url)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{mcp_url}/api/v1/mcp/search",
            params={"query": query, "top_k": top_k},
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


async def search_kubernetes_documentation(
    query: str,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Search official Kubernetes reference documentation via `mcp-k8s-docs-server`.

    Supports both:
    - Standalone MCP Microservice mode (when `MCP_SERVER_URL` is configured, authenticating
      with the Agent's `k8s-copilot-sa` OIDC ID token and `X-Agent-Spiffe-Id` header).
    - Co-located in-process mode (for low-latency local development and sandbox execution).
    """
    active_mcp_url = config_mod.MCP_SERVER_URL
    if active_mcp_url:
        mcp_response = await _call_remote_mcp_microservice(active_mcp_url, query=query, top_k=3)
    else:
        mcp_response = await mcp_search_kubernetes_documentation(query=query, top_k=3)

    results = mcp_response.get("results", [])

    if tool_context is not None:
        existing_citations = list(tool_context.state.get("source_citations") or [])
        for entry in results:
            url = entry.get("url")
            bcrumb = entry.get("breadcrumb")
            if url:
                citation_str = f"{bcrumb} ({url})" if bcrumb and bcrumb not in url else url
                if citation_str not in existing_citations:
                    existing_citations.append(citation_str)
        tool_context.state["source_citations"] = existing_citations

    return {
        "status": mcp_response.get("status", "success"),
        "mcp_server": mcp_server.name,
        "datastore": mcp_response.get("datastore", DATASTORE_ID),
        "query": query,
        "results": results,
    }


