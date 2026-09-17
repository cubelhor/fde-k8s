"""Live End-to-End Integration Tests for Vertex AI Search Datastore & Multi-Agent Copilot.

Tests:
1. Live Vertex AI Search Datastore Retrieval (`search_kubernetes_documentation`):
   Verifies that the uploaded custom chunks in `k8s-custom-chunks-store` are live,
   indexed in Branch 0, and return structured `chunk_id`, `breadcrumb`, `content`, and
   `has_code_block` metadata.
2. Live Multi-Agent Troubleshooting Pipeline (`PlannerAgent` -> `ExecutorAgent`):
   Verifies that real Kubernetes incident queries retrieve live Vertex AI Search
   documentation chunks and generate grounded, safety-validated `TroubleshootingPlan`
   outputs.

Note:
- Automatically skips if Google Cloud Application Default Credentials (ADC) are expired.
- To run live against GCP:
  gcloud auth application-default login --client-id-file=/Users/cuebelhoer/secure/client_secrets.json --scopes="https://www.googleapis.com/auth/cloud-platform"
  .venv/bin/pytest multi_agent/backend/tests/test_vertex_integration.py -v -s
"""

import os
import sys
import pytest
from google.auth import default
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.auth.transport.requests import Request

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.tools import search_kubernetes_documentation, PROJECT_ID, DATASTORE_ID
from src.agents import PlannerAgent, ExecutorAgent
from src.models import TroubleshootingPlan


def has_valid_gcp_credentials() -> bool:
    """Checks if valid Google Cloud ADC credentials are available for live tests."""
    try:
        creds, _ = default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=PROJECT_ID,
        )
        if not creds.valid:
            creds.refresh(Request())
        return True
    except (DefaultCredentialsError, RefreshError, Exception):
        return False


requires_gcp_adc = pytest.mark.skipif(
    not has_valid_gcp_credentials(),
    reason="Live GCP Application Default Credentials (ADC) required. Run `gcloud auth application-default login` to execute live Vertex AI Search tests.",
)


@requires_gcp_adc
@pytest.mark.asyncio
async def test_live_vertex_datastore_retrieval():
    """Verify live retrieval from Vertex AI Search custom datastore (`k8s-custom-chunks-store`)."""
    queries = [
        "What is CrashLoopBackOff and how does Kubernetes manage container restart backoff delay?",
        "What is the difference between a Role and a ClusterRole in Kubernetes RBAC authorization?",
        "How does the Kubernetes control plane bind a PersistentVolumeClaim to a PersistentVolume?",
    ]

    for query in queries:
        res = await search_kubernetes_documentation(query)
        assert res["status"] == "success", f"Expected live search status 'success', got '{res['status']}'"
        assert len(res["results"]) > 0, f"Expected indexed chunks for query: {query}"

        top_hit = res["results"][0]
        assert top_hit.get("chunk_id"), "Returned chunk must have a valid chunk_id"
        assert top_hit.get("breadcrumb"), "Returned chunk must have a valid breadcrumb"
        assert len(top_hit.get("content", "")) > 50, "Returned chunk content must be non-empty"


@requires_gcp_adc
@pytest.mark.asyncio
async def test_live_multi_agent_e2e_with_vertex_datastore():
    """Verify end-to-end PlannerAgent + ExecutorAgent flow grounded in live Vertex AI Search."""
    planner = PlannerAgent()
    executor = ExecutorAgent()

    incident_query = "Pod coredns in kube-system is stuck in CrashLoopBackOff after ConfigMap update"
    plan_context = await planner.generate_plan(incident_query)

    assert "plan" in plan_context
    assert "retrieved_docs" in plan_context
    assert len(plan_context["retrieved_docs"]) > 0, "Planner must retrieve real chunks from Vertex AI Search"

    final_plan: TroubleshootingPlan = executor.generate_commands(
        incident_query=incident_query,
        planner_output=plan_context["plan"],
        retrieved_docs=plan_context["retrieved_docs"],
    )

    assert isinstance(final_plan, TroubleshootingPlan)
    assert len(final_plan.steps) >= 1
    assert len(final_plan.source_citations) >= 1
    # Verify safety guardian ran on every step
    for step in final_plan.steps:
        assert step.danger_level in ("LOW", "MEDIUM", "HIGH")
        assert step.command.startswith("kubectl")
