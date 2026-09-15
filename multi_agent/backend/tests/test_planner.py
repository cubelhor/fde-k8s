"""Unit tests for the PlannerAgent, ADK Runner event stream, and async Vertex AI Search (Discovery Engine) tools."""

import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock
import pytest

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from google.adk.events import Event
from google.genai import types
from src.models import IncidentState
from src.agents import PlannerAgent, create_planner_agent
from src.tools import search_kubernetes_documentation


@pytest.mark.asyncio
async def test_search_kubernetes_documentation_mocked():
    """Test that the async search_kubernetes_documentation tool queries Discovery Engine and formats snippets."""
    mock_search_client = MagicMock()

    # Create mock document with derived_struct_data
    mock_doc = MagicMock()
    mock_doc.id = "doc-oom-guide"
    mock_doc.derived_struct_data = {
        "title": "Configure Memory and CPU Quotas",
        "link": "https://kubernetes.io/docs/tasks/administer-cluster/manage-resources/memory-default-namespace/",
        "snippets": [{"snippet": "Assign memory resource limits and requests to containers."}]
    }

    mock_result_item = MagicMock()
    mock_result_item.document = mock_doc

    # Create an async iterator for the SearchResponse
    class AsyncSearchIterator:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            self._iter = iter(self.items)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    mock_search_client.search = AsyncMock(return_value=AsyncSearchIterator([mock_result_item]))

    with patch("google.cloud.discoveryengine_v1beta.SearchServiceAsyncClient", return_value=mock_search_client):
        result = await search_kubernetes_documentation("OOMKilled")

        assert result["status"] == "success"
        assert result["query"] == "OOMKilled"
        assert len(result["results"]) == 1
        assert result["results"][0]["title"] == "Configure Memory and CPU Quotas"
        assert result["results"][0]["url"].startswith("https://kubernetes.io/")
        assert "memory resource limits" in result["results"][0]["snippet"]


@pytest.mark.asyncio
async def test_search_kubernetes_documentation_struct_data():
    """Test that search_kubernetes_documentation extracts struct_data fields from k8s-custom-chunks-store."""
    mock_search_client = MagicMock()

    mock_doc = MagicMock()
    mock_doc.id = "chunk-admission-001"
    mock_doc.struct_data = {
        "breadcrumb": "Admission Control in Kubernetes > What are they?",
        "doc_path": "content/en/docs/reference/access-authn-authz/admission-controllers.md",
        "content": "An admission controller is a piece of code that intercepts requests to the Kubernetes API server.",
        "has_code_block": True,
    }
    mock_doc.derived_struct_data = {}

    mock_result_item = MagicMock()
    mock_result_item.document = mock_doc

    class AsyncSearchIterator:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            self._iter = iter(self.items)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration

    mock_search_client.search = AsyncMock(return_value=AsyncSearchIterator([mock_result_item]))

    with patch("google.cloud.discoveryengine_v1beta.SearchServiceAsyncClient", return_value=mock_search_client):
        result = await search_kubernetes_documentation("admission controller")

        assert result["status"] == "success"
        assert len(result["results"]) == 1
        item = result["results"][0]
        assert item["chunk_id"] == "chunk-admission-001"
        assert item["breadcrumb"] == "Admission Control in Kubernetes > What are they?"
        assert item["doc_path"] == "content/en/docs/reference/access-authn-authz/admission-controllers.md"
        assert "intercepts requests to the Kubernetes API server" in item["content"]
        assert item["has_code_block"] is True


@pytest.mark.asyncio
async def test_planner_agent_adk_runner_plan_execution():
    """Test that PlannerAgent.plan() executes via the ADK Runner, extracts event text, and populates checklist."""
    mock_runner = MagicMock()

    mock_checklist_text = """1. Inspect pod memory usage and last termination state using kubectl describe pod.
2. Check recent node memory pressure events in the namespace.
3. Identify memory leak culprits from container logs.
4. Scale deployment or increase pod memory limits to 1Gi in manifest."""

    # Async generator simulating ADK Runner event stream
    async def mock_run_async(*args, **kwargs):
        yield Event(
            content=types.Content(
                parts=[types.Part.from_text(text=mock_checklist_text)]
            )
        )

    mock_runner.run_async = mock_run_async

    planner = PlannerAgent(runner=mock_runner)

    initial_state = IncidentState(
        incident_id="inc-oom-9921",
        raw_logs="Pod auth-service-6d8b in CrashLoopBackOff: exit code 137 (OOMKilled) after reaching 512Mi limit",
        cluster_context="gke-prod-europe-west4-prod-cluster",
        status="INITIALIZED"
    )

    result_state = await planner.plan(initial_state)

    # 1. Verify state status update
    assert result_state.status == "PLANNING_COMPLETED"

    # 2. Verify planner checklist is populated with clean checklist steps from ADK events
    assert isinstance(result_state.planner_checklist, list)
    assert len(result_state.planner_checklist) == 4
    assert result_state.planner_checklist[0].startswith("1. Inspect pod memory")
    assert result_state.planner_checklist[3].startswith("4. Scale deployment")
