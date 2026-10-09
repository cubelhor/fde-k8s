"""MCP Server (`mcp-k8s-docs-server`) for Vertex AI Search Kubernetes Documentation.

Implements the Model Context Protocol (MCP) server specified in `design.md` (§3 Agent 1):
- Server Name: `mcp-k8s-docs-server` (via Anthropic `FastMCP`)
- Tool: `search_kubernetes_documentation`
- Transports: `stdio` and `sse` (Server-Sent Events)
- Backend: Google Cloud Vertex AI Search (`k8s-custom-chunks-store`) with a lazy-loaded
  `SearchServiceAsyncClient` gRPC singleton.
"""

import asyncio
import argparse
from typing import Dict, Any, Optional

from google.cloud import discoveryengine_v1beta
from mcp.server.fastmcp import FastMCP

from src.auth import get_gcp_credentials
from src.config import PROJECT_ID, DISCOVERY_ENGINE_LOCATION as LOCATION, DATASTORE_ID

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
# Lazy-Loaded gRPC Client Singleton (Zero Per-Request Churn)
# ============================================================================

_search_client: Optional[discoveryengine_v1beta.SearchServiceAsyncClient] = None
_search_client_loop = None


def _get_search_client() -> discoveryengine_v1beta.SearchServiceAsyncClient:
    """Returns a persistent SearchServiceAsyncClient singleton per active event loop to reuse gRPC channels across queries."""
    global _search_client, _search_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None
    if _search_client is None or _search_client_loop is not current_loop:
        creds, _ = get_gcp_credentials(project_id=PROJECT_ID)
        _search_client = discoveryengine_v1beta.SearchServiceAsyncClient(credentials=creds)
        _search_client_loop = current_loop
    return _search_client


# ============================================================================
# Registered FastMCP Tool & Vertex AI Search Query
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
    """Queries Vertex AI Search (`k8s-custom-chunks-store`) via SearchServiceAsyncClient."""
    client = _get_search_client()

    req = discoveryengine_v1beta.SearchRequest(
        serving_config=SERVING_CONFIG_PATH,
        query=query,
        page_size=top_k,
        query_expansion_spec=discoveryengine_v1beta.SearchRequest.QueryExpansionSpec(
            condition=discoveryengine_v1beta.SearchRequest.QueryExpansionSpec.Condition.AUTO,
        ),
        spell_correction_spec=discoveryengine_v1beta.SearchRequest.SpellCorrectionSpec(
            mode=discoveryengine_v1beta.SearchRequest.SpellCorrectionSpec.Mode.AUTO,
        ),
    )

    response = await client.search(request=req, timeout=4.0)
    results = []

    async for r in response:
        struct = dict(r.document.struct_data) if getattr(r.document, "struct_data", None) else {}

        chunk_id = struct.get("_id") or struct.get("id") or r.document.id
        breadcrumb = struct.get("breadcrumb") or struct.get("title") or chunk_id
        url = struct.get("url") or "https://kubernetes.io/docs/reference/"
        content = struct.get("content", "")

        results.append({
            "chunk_id": chunk_id,
            "breadcrumb": breadcrumb,
            "url": url,
            "content": content,
            "has_code_block": bool(struct.get("has_code_block", False)),
        })
        if len(results) >= top_k:
            break

    return {
        "status": "success",
        "server": mcp_server.name,
        "datastore": DATASTORE_ID,
        "query": query,
        "results": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run mcp-k8s-docs-server over stdio or SSE.")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="MCP transport protocol")
    args = parser.parse_args()
    mcp_server.run(transport=args.transport)
