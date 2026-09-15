"""Async Tools for the Kubernetes Troubleshooting Copilot.

Integrates Vertex AI Search (Discovery Engine) for documentation retrieval.
"""

import os
import logging
from typing import Dict, Any, List

from google.cloud import discoveryengine_v1beta
from google.auth import default

logger = logging.getLogger("k8s_tools")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "europe-west4")
DATASTORE_ID = os.getenv("DISCOVERY_ENGINE_DATASTORE_ID", "k8s-custom-chunks-store")


async def search_kubernetes_documentation(query: str) -> Dict[str, Any]:
    """Search official Kubernetes reference documentation and runbooks asynchronously.
    
    Args:
        query: Specific technical query or error keyword (e.g. 'CrashLoopBackOff', 'OOMKilled', 'CoreDNS').
        
    Returns:
        A dictionary containing relevant documentation snippets, titles, and source URLs.
    """
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
                snippet_spec=discoveryengine_v1beta.SearchRequest.ContentSearchSpec.SnippetSpec(return_snippet=True)
            )
        )
        
        response = await client.search(request=req)
        results = []
        
        # Async iterator across SearchResponse results
        async for r in response:
            struct = dict(r.document.struct_data) if getattr(r.document, "struct_data", None) else {}
            derived = dict(r.document.derived_struct_data) if getattr(r.document, "derived_struct_data", None) else {}

            chunk_id = struct.get("id") or struct.get("_id") or r.document.id
            breadcrumb = struct.get("breadcrumb") or struct.get("title") or derived.get("title") or chunk_id
            doc_path = struct.get("url") or struct.get("uri") or struct.get("doc_path") or derived.get("link") or "https://kubernetes.io/docs/reference/"
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
            })
            
        return {
            "status": "success",
            "query": query,
            "results": results
        }
    except Exception as exc:
        logger.warning(f"Discovery Engine search fallback (Offline/Mock): {exc}")
        return {
            "status": "fallback",
            "query": query,
            "results": [
                {
                    "title": f"Kubernetes Troubleshooting Guide for {query}",
                    "url": "https://kubernetes.io/docs/tasks/debug/",
                    "snippet": f"Official documentation and triage steps for resolving {query} in production clusters."
                }
            ]
        }
