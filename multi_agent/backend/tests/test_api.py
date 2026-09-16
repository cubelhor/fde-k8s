"""Integration tests for the FastAPI backend API endpoints and multi-agent pipeline."""

import os
import sys
from unittest.mock import MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from src.models import (
    DiagnoseRequest,
    DiagnoseResponse,
    IncidentState,
    TroubleshootingPlan,
    KubectlCommand,
)
from src.agents import PlannerAgent, ExecutorAgent
from main import app, get_planner_agent, get_executor_agent


@pytest.fixture
def mock_planner():
    planner = MagicMock(spec=PlannerAgent)
    
    async def mock_plan(state: IncidentState) -> IncidentState:
        state.planner_checklist = [
            "1. Inspect pod memory usage with kubectl describe pod.",
            "2. Check node memory pressure events in cluster.",
            "3. Scale deployment to distribute load.",
            "4. Delete crashed pod to force recreation."
        ]
        state.status = "PLANNING_COMPLETED"
        return state
        
    planner.plan = AsyncMock(side_effect=mock_plan)
    return planner


@pytest.fixture
def mock_executor():
    executor = MagicMock(spec=ExecutorAgent)
    
    async def mock_execute(state: IncidentState) -> IncidentState:
        state.raw_command = [
            KubectlCommand(
                step_number=1,
                title="Describe pod",
                command="kubectl describe pod auth-api-5d7f -n prod",
                explanation="Inspect termination state.",
                danger_level="LOW"
            ),
            KubectlCommand(
                step_number=2,
                title="Scale deployment",
                command="kubectl scale deployment auth-api --replicas=4 -n prod",
                explanation="Scale deployment replicas.",
                danger_level="MEDIUM"
            ),
            KubectlCommand(
                step_number=3,
                title="Delete pod",
                command="kubectl delete pod auth-api-5d7f -n prod",
                explanation="Force pod recreation. ⚠️ WARNING: Destructive action.",
                danger_level="HIGH"
            ),
        ]
        state.final_validated_command = state.raw_command
        state.status = "EXECUTED"
        return state
        
    executor.execute = AsyncMock(side_effect=mock_execute)
    return executor


def test_root_endpoint():
    """Verify root endpoint returns service metadata."""
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["service"] == "kubernetes-troubleshooting-copilot"
    assert data["status"] == "online"
    assert "planner" in data["agents"]


def test_healthz_endpoint():
    """Verify healthz probe returns 200 OK."""
    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy"}


def test_diagnose_pipeline_success(mock_planner, mock_executor):
    """Verify full POST /api/v1/diagnose multi-agent orchestration pipeline."""
    app.dependency_overrides[get_planner_agent] = lambda: mock_planner
    app.dependency_overrides[get_executor_agent] = lambda: mock_executor

    try:
        client = TestClient(app)
        payload = {
            "raw_logs": "Pod auth-api-5d7f in CrashLoopBackOff: exit code 137 OOMKilled",
            "cluster_context": "gke-prod-europe-west4",
            "incident_id": "inc-test-8899"
        }
        res = client.post("/api/v1/diagnose", json=payload)
        assert res.status_code == 200
        data = res.json()

        # 1. Assert Response Structure
        assert data["success"] is True
        assert data["error"] is None
        assert "plan" in data
        assert "state" in data

        # 2. Assert TroubleshootingPlan
        plan = data["plan"]
        assert len(plan["steps"]) == 3
        assert plan["steps"][0]["danger_level"] == "LOW"
        assert plan["steps"][1]["danger_level"] == "MEDIUM"
        assert plan["steps"][2]["danger_level"] == "HIGH"
        assert "WARNING: Destructive action" in plan["steps"][2]["explanation"]

        # 3. Assert IncidentState Trajectory
        state = data["state"]
        assert state["incident_id"] == "inc-test-8899"
        assert state["status"] == "COMPLETED"
        assert len(state["planner_checklist"]) == 4

        # 4. Assert mock calls
        mock_planner.plan.assert_called_once()
        mock_executor.execute.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_feedback_endpoint():
    """Verify SRE feedback submission."""
    client = TestClient(app)
    payload = {
        "incident_id": "inc-test-8899",
        "rating": "thumbs_up",
        "comments": "Accurate diagnostic steps and safe alternatives provided."
    }
    res = client.post("/api/v1/feedback", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "inc-test-8899" in data["message"]


def test_mcp_server_status_endpoint():
    """Verify MCP Server (mcp-k8s-docs-server) status, SPIFFE identity metadata, and tool registration."""
    client = TestClient(app)
    res = client.get("/api/v1/mcp/status")
    assert res.status_code == 200
    data = res.json()
    assert data["server_name"] == "mcp-k8s-docs-server"
    assert "stdio" in data["transports"]
    assert "sse" in data["transports"]
    assert "auth" in data
    assert data["auth"]["spiffe_id"].startswith("spiffe://")
    assert data["auth"]["secret_manager_enabled"] is True
    tool_names = [t["name"] for t in data["tools"]]
    assert tool_names == ["search_kubernetes_documentation"]


def test_secret_manager_and_spiffe_auth():
    """Verify Google Cloud Secret Manager lookup and SPIFFE Workload Identity configuration in src.auth."""
    from unittest.mock import patch
    import src.auth as auth_mod

    # Reset cache for test isolation
    auth_mod._secret_cache.clear()
    auth_mod._secret_client = None

    mock_secret_response = MagicMock()
    mock_secret_response.payload.data = b"otel-collector-secret-api-key-999"

    mock_sm_client = MagicMock()
    mock_sm_client.access_secret_version.return_value = mock_secret_response

    with patch("src.auth._get_secret_manager_client", return_value=mock_sm_client):
        secret_val = auth_mod.get_secret("telemetry-collector-api-key")
        assert secret_val == "otel-collector-secret-api-key-999"
        mock_sm_client.access_secret_version.assert_called_once()

        # Verify subsequent call uses in-memory cache without another RPC call
        cached_val = auth_mod.get_secret("telemetry-collector-api-key")
        assert cached_val == "otel-collector-secret-api-key-999"
        assert mock_sm_client.access_secret_version.call_count == 1


def test_mcp_server_search_endpoint():
    """Verify MCP Server search endpoint returns real chunks with breadcrumbs and URLs."""
    client = TestClient(app)
    res = client.get("/api/v1/mcp/search", params={"query": "CrashLoopBackOff container restartPolicy", "top_k": 2})
    assert res.status_code == 200
    data = res.json()
    assert data["server"] == "mcp-k8s-docs-server"
    assert len(data["results"]) >= 1
    first_chunk = data["results"][0]
    assert "chunk_id" in first_chunk
    assert "breadcrumb" in first_chunk
    assert "url" in first_chunk
    assert first_chunk["url"].startswith("https://kubernetes.io/")
