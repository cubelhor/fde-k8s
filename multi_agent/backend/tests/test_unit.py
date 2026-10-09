"""Deterministic Unit Test Suite for Kubernetes Troubleshooting Copilot Backend.

Achieves >90% code coverage across `src/` and `main.py` with mocked GCP/LLM
dependencies for fast, offline CI verification alongside `test_evals.py`.
"""

import os
import sys
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Ensure backend root is on sys.path
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import src.auth as auth_mod
import src.mcp_server as mcp_mod
import src.telemetry as telemetry_mod
from src.agents import (
    load_prompt,
    planner_after_callback,
    executor_before_callback,
    executor_after_callback,
    _extract_usage_tokens,
    run_agent_pipeline,
    planner_agent,
    executor_agent,
    root_orchestrator,
)
from src.models import IncidentState, TroubleshootingPlan, KubectlCommand
from src.tools import search_kubernetes_documentation
from main import app, StructuredJsonFormatter, lifespan


# ============================================================================
# 1. Agents & Lifecycle Callbacks (`src/agents.py`)
# ============================================================================

def test_load_prompts_and_extract_usage_tokens():
    planner_prompt = load_prompt("planner_v1.yaml")
    executor_prompt = load_prompt("executor_v1.yaml")
    assert "SCOPE LOCK" in planner_prompt
    assert "{planner_checklist?}" in executor_prompt

    # Missing usage_metadata
    assert _extract_usage_tokens(SimpleNamespace()) == {
        "prompt_tokens": 0,
        "cached_tokens": 0,
        "completion_tokens": 0,
    }

    # Valid usage_metadata + boolean guard
    event = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=120,
            cached_content_token_count=True,
            candidates_token_count=45,
        )
    )
    assert _extract_usage_tokens(event) == {
        "prompt_tokens": 120,
        "cached_tokens": 0,
        "completion_tokens": 45,
    }


def test_planner_and_executor_after_callbacks():
    ctx = SimpleNamespace(state={"planner_checklist": "1. Step A\n\n2. Step B\n"})
    planner_after_callback(ctx)
    assert ctx.state["planner_checklist"] == ["1. Step A", "2. Step B"]
    assert ctx.state["status"] == "PLANNING_COMPLETED"

    # Normal checklist -> executor_before_callback returns None (proceeds to LLM)
    assert executor_before_callback(ctx) is None

    # Scope Lock checklist -> executor_before_callback short-circuits Executor LLM call
    scope_ctx = SimpleNamespace(
        state={"planner_checklist": ["Error: Query is out of scope. Please provide a Kubernetes-related issue."]}
    )
    short_circuit_content = executor_before_callback(scope_ctx)
    assert short_circuit_content is not None
    assert scope_ctx.state["status"] == "COMPLETED"
    assert scope_ctx.state["troubleshooting_plan"]["steps"] == []

    # Executor callback with JSON string plan and empty citations fallback
    raw_plan = TroubleshootingPlan(
        problem_summary="OOMKilled pod",
        error_type="OOMKilled",
        steps=[
            KubectlCommand(
                step_number=1,
                title="Delete pod",
                command="kubectl delete pod app-1",
                explanation="Delete crashing pod.",
                danger_level="LOW",
            ),
            KubectlCommand(
                step_number=2,
                title="Scale deployment",
                command="kubectl scale deployment app --replicas=2",
                explanation="Scale deployment.",
                danger_level="LOW",
            ),
            KubectlCommand(
                step_number=3,
                title="Check pods",
                command="kubectl get pods",
                explanation="List pods.",
                danger_level="HIGH",
            ),
            KubectlCommand(
                step_number=4,
                title="Port forward",
                command="kubectl port-forward pod/app-1 8080:80",
                explanation="Forward local port.",
                danger_level="LOW",
            ),
        ],
        source_citations=[],
    ).model_dump_json()

    exec_ctx = SimpleNamespace(state={"troubleshooting_plan": raw_plan})
    executor_after_callback(exec_ctx)
    assert exec_ctx.state["status"] == "COMPLETED"
    validated = exec_ctx.state["troubleshooting_plan"]
    assert validated["steps"][0]["danger_level"] == "HIGH"
    assert "WARNING: Destructive action" in validated["steps"][0]["explanation"]
    assert validated["steps"][1]["danger_level"] == "MEDIUM"
    assert validated["steps"][2]["danger_level"] == "LOW"
    assert validated["steps"][3]["danger_level"] == "MEDIUM"
    assert len(validated["source_citations"]) == 2


@pytest.mark.asyncio
async def test_run_agent_pipeline_branches():
    fake_plan = TroubleshootingPlan(
        problem_summary="Pod crash",
        error_type="CrashLoopBackOff",
        steps=[
            KubectlCommand(
                step_number=1,
                title="Logs",
                command="kubectl logs pod-1",
                explanation="Check logs",
                danger_level="LOW",
            )
        ],
        source_citations=["https://kubernetes.io/docs/concepts/"],
    )

    async def _fake_run_async(user_id: str, session_id: str, new_message):
        yield SimpleNamespace(
            author="planner_agent",
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                cached_content_token_count=20,
                candidates_token_count=30,
            ),
        )
        yield SimpleNamespace(
            author="executor_agent",
            usage_metadata=SimpleNamespace(
                prompt_token_count=80,
                cached_content_token_count=0,
                candidates_token_count=40,
            ),
        )

    import src.agents as src_agents

    fake_updated_session = SimpleNamespace(
        state={
            "incident_id": "u-1",
            "raw_logs": "crash",
            "planner_checklist": ["1. Check logs"],
            "troubleshooting_plan": fake_plan.model_dump(),
            "status": "COMPLETED",
            "metadata": {},
        }
    )

    with patch.object(src_agents.default_runner, "run_async", side_effect=_fake_run_async), \
         patch.object(src_agents.planner_runner, "run_async", side_effect=_fake_run_async), \
         patch.object(src_agents.session_service, "get_session", new=AsyncMock(return_value=fake_updated_session)), \
         patch("src.agents.Runner") as mock_runner_cls:
        mock_instance = MagicMock()
        mock_instance.run_async = _fake_run_async
        mock_runner_cls.return_value = mock_instance

        # 1. Default root_orchestrator branch
        state1 = await run_agent_pipeline(IncidentState(incident_id="u-1", raw_logs="crash"), agent=root_orchestrator)
        assert state1.status == "COMPLETED"
        assert state1.metadata["prompt_tokens"] == 180
        assert state1.metadata["cached_tokens"] == 20
        assert state1.metadata["completion_tokens"] == 70
        assert "planner_latency_ms" in state1.metadata
        assert "executor_latency_ms" in state1.metadata

        # 2. Standalone planner_agent branch
        state2 = await run_agent_pipeline(IncidentState(incident_id="u-2", raw_logs="crash"), agent=planner_agent)
        assert state2.status == "COMPLETED"

        # 3. Custom agent branch (executor_agent)
        state3 = await run_agent_pipeline(IncidentState(incident_id="u-3", raw_logs="crash"), agent=executor_agent)
        assert state3.status == "COMPLETED"



# ============================================================================
# 2. Authentication, SPIFFE & Secret Manager (`src/auth.py`)
# ============================================================================

def test_auth_spiffe_and_adc_flows(tmp_path, monkeypatch):
    auth_mod._cached_credentials = None
    auth_mod._secret_client = None
    auth_mod._secret_cache.clear()

    svid_file = tmp_path / "svid.jwt"
    svid_file.write_text("dummy-jwt", encoding="utf-8")
    monkeypatch.setattr(auth_mod, "DEFAULT_SVID_TOKEN_PATH", str(svid_file))
    monkeypatch.setenv("SPIFFE_WIP_AUDIENCE", "//iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/p/providers/pr")

    mock_creds = MagicMock()
    with patch("src.auth.identity_pool.Credentials.from_info", return_value=mock_creds):
        creds, mode = auth_mod.get_gcp_credentials()
        assert creds is mock_creds
        assert mode == "spiffe_workload_identity_federation"
        # Cached hit
        creds2, mode2 = auth_mod.get_gcp_credentials()
        assert creds2 is mock_creds
        assert mode2 == "spiffe_workload_identity_federation"

    # Exception in SPIFFE -> fallback to google.auth.default with K_SERVICE
    auth_mod._cached_credentials = None
    monkeypatch.setenv("K_SERVICE", "k8s-copilot")
    with patch("src.auth.identity_pool.Credentials.from_info", side_effect=ValueError("bad svid")), \
         patch("src.auth.google.auth.default", return_value=(mock_creds, "proj")):
        creds, mode = auth_mod.get_gcp_credentials()
        assert mode == "spiffe_gke_cloudrun_workload_identity"

    meta = auth_mod.get_identity_metadata()
    assert meta["identity_mode"] == "spiffe_gke_cloudrun_workload_identity"

    # Offline fallback in get_identity_metadata
    auth_mod._cached_credentials = None
    with patch("src.auth.get_gcp_credentials", side_effect=RuntimeError("no creds")):
        assert auth_mod.get_identity_metadata()["identity_mode"] == "offline_fallback"


def test_secret_manager_and_env_fallback(monkeypatch):
    auth_mod._secret_client = None
    auth_mod._secret_cache.clear()

    mock_sm_client = MagicMock()
    mock_sm_client.access_secret_version.return_value = SimpleNamespace(
        payload=SimpleNamespace(data=b"  secret-val-123 \n")
    )
    with patch("src.auth.get_gcp_credentials", return_value=(MagicMock(), "adc")), \
         patch("src.auth.secretmanager.SecretManagerServiceClient", return_value=mock_sm_client):
        val = auth_mod.get_secret("my-secret")
        assert val == "secret-val-123"
        # Cache hit
        assert auth_mod.get_secret("my-secret") == "secret-val-123"

    # Fallback to default_env_var when Secret Manager raises
    auth_mod._secret_cache.clear()
    mock_sm_client.access_secret_version.side_effect = RuntimeError("sm offline")
    monkeypatch.setenv("CUSTOM_ENV_KEY", "fallback-env-val")
    with patch("src.auth._get_secret_manager_client", return_value=mock_sm_client):
        assert auth_mod.get_secret("other-secret", default_env_var="CUSTOM_ENV_KEY") == "fallback-env-val"
        monkeypatch.setenv("THIRD_SECRET", "upper-val")
        assert auth_mod.get_secret("third-secret") == "upper-val"

    # Multi-Hop 1: End-User OIDC / IAP JWT verification
    with patch("src.auth.google_id_token.verify_oauth2_token", return_value={"email": "sre@company.com", "sub": "u-1"}):
        u_iap = auth_mod.verify_end_user_identity(iap_jwt="iap-token-123")
        assert u_iap["authenticated"] is True
        assert u_iap["email"] == "sre@company.com"

        u_bearer = auth_mod.verify_end_user_identity(authorization="Bearer oidc-token-123")
        assert u_bearer["source"] == "oidc_bearer_token"

    monkeypatch.setattr(auth_mod, "REQUIRE_END_USER_AUTH", True)
    with pytest.raises(PermissionError):
        auth_mod.verify_end_user_identity()
    with patch("src.auth.google_id_token.verify_oauth2_token", side_effect=ValueError("expired")):
        with pytest.raises(PermissionError):
            auth_mod.verify_end_user_identity(authorization="Bearer bad")
    monkeypatch.setattr(auth_mod, "REQUIRE_END_USER_AUTH", False)

    # Multi-Hop 2 & 3: Agent ID Token & Agent Gateway verification
    with patch("src.auth.google_id_token.fetch_id_token", return_value="agent-oidc-jwt"):
        monkeypatch.setattr(auth_mod, "DEFAULT_SVID_TOKEN_PATH", "/nonexistent/svid.jwt")
        assert auth_mod.fetch_agent_id_token("https://mcp.run.app") == "agent-oidc-jwt"

    with patch(
        "src.auth.google_id_token.verify_oauth2_token",
        return_value={"email": auth_mod.ALLOWED_AGENT_SA_EMAIL, "sub": "sa-1"},
    ):
        gw_ok = auth_mod.verify_agent_gateway_token(
            authorization="Bearer good-agent-jwt",
            spiffe_id_header=auth_mod.DEFAULT_SPIFFE_ID,
        )
        assert gw_ok["authorized"] is True
        assert gw_ok["mode"] == "verified_oidc_agent_identity"

        with pytest.raises(PermissionError):
            auth_mod.verify_agent_gateway_token(
                authorization="Bearer good-agent-jwt",
                spiffe_id_header="spiffe://wrong/sa/rogue",
            )

    with patch(
        "src.auth.google_id_token.verify_oauth2_token",
        return_value={"email": "rogue-sa@other.iam.gserviceaccount.com"},
    ):
        with pytest.raises(PermissionError):
            auth_mod.verify_agent_gateway_token(authorization="Bearer rogue-jwt")


# ============================================================================
# 3. Telemetry Sinks (`src/telemetry.py`)
# ============================================================================

@pytest.mark.asyncio
async def test_telemetry_bigquery_and_firestore(monkeypatch):
    telemetry_mod._firestore_async_client = None

    bq_res = telemetry_mod.record_token_metrics_to_bigquery(
        incident_id="inc-t1",
        model_name="gemini-2.5-pro",
        prompt_tokens=2000,
        cached_tokens=1000,
        completion_tokens=500,
        checklist_steps=5,
        validated_commands=3,
        latency_ms=1234.56,
    )
    assert bq_res["persisted"] is True
    assert bq_res["row"]["total_tokens"] == 2500

    # Local structured log mode (sinks disabled)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("ENABLE_GCP_SINKS", "false")
    fs_local = await telemetry_mod.record_feedback_to_firestore(
        incident_id="inc-t1",
        rating="thumbs_up",
        comment="Great plan",
        copied_command="kubectl get pods",
        step_number=1,
        session_duration_sec=42.5,
    )
    assert fs_local["sink"] == "structured_log"

    # Firestore enabled mode
    monkeypatch.setenv("ENABLE_GCP_SINKS", "true")
    mock_doc_ref = MagicMock()
    mock_doc_ref.set = AsyncMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc_ref

    with patch("src.telemetry.get_gcp_credentials", return_value=(MagicMock(), "proj")), \
         patch("google.cloud.firestore.AsyncClient", return_value=mock_db):
        fs_live = await telemetry_mod.record_feedback_to_firestore(
            incident_id="inc-t2",
            rating="thumbs_down",
            copied_command="kubectl describe pod x",
            step_number=2,
            session_duration_sec=15.0,
        )
        assert fs_live["sink"] == "firestore"
        mock_doc_ref.set.assert_awaited_once()

        # Firestore error fallback
        mock_doc_ref.set.side_effect = RuntimeError("firestore down")
        fs_err = await telemetry_mod.record_feedback_to_firestore(incident_id="inc-t3", rating="thumbs_up")
        assert fs_err["sink"] == "structured_log_fallback"


# ============================================================================
# 4. MCP Server & ADK Search Tool (`src/mcp_server.py` & `src/tools.py`)
# ============================================================================

@pytest.mark.asyncio
async def test_mcp_server_and_search_tool(monkeypatch):
    mcp_mod._search_client = None

    doc1 = SimpleNamespace(
        document=SimpleNamespace(
            id="doc-1",
            struct_data={
                "_id": "chunk-1",
                "breadcrumb": "Pods > OOMKilled",
                "url": "https://kubernetes.io/docs/concepts/workloads/pods/",
                "content": "Exit code 137 indicates OOMKilled.",
                "has_code_block": True,
            },
        )
    )
    doc2 = SimpleNamespace(
        document=SimpleNamespace(
            id="doc-2",
            struct_data={
                "_id": "chunk-2",
                "title": "Debug Pods",
                "url": "https://kubernetes.io/docs/tasks/debug/",
                "content": "Use kubectl describe pod.",
            },
        )
    )

    async def _mock_pager():
        yield doc1
        yield doc2

    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=_mock_pager())

    with patch("src.mcp_server.get_gcp_credentials", return_value=(MagicMock(), "adc")), \
         patch("src.mcp_server.discoveryengine_v1beta.SearchServiceAsyncClient", return_value=mock_client):
        ctx = SimpleNamespace(state={})
        tool_res = await search_kubernetes_documentation("OOMKilled", tool_context=ctx)
        assert tool_res["status"] == "success"
        assert len(tool_res["results"]) == 2
        assert "retrieved_docs" not in ctx.state
        assert len(ctx.state["source_citations"]) == 2

    # Test Standalone Remote MCP Microservice mode (`MCP_SERVER_URL` configured)
    monkeypatch.setattr("src.config.MCP_SERVER_URL", "https://mcp-service.run.app")
    mock_http_resp = MagicMock()
    mock_http_resp.raise_for_status = MagicMock()
    mock_http_resp.json.return_value = {
        "status": "success",
        "results": [
            {
                "chunk_id": "remote-1",
                "breadcrumb": "Remote > Doc",
                "url": "https://kubernetes.io/docs/concepts/",
                "content": "Remote chunk content.",
            }
        ],
    }
    mock_async_http = MagicMock()
    mock_async_http.__aenter__ = AsyncMock(return_value=mock_async_http)
    mock_async_http.__aexit__ = AsyncMock(return_value=None)
    mock_async_http.get = AsyncMock(return_value=mock_http_resp)

    with patch("src.tools.fetch_agent_id_token", return_value="agent-token-xyz"), \
         patch("src.tools.httpx.AsyncClient", return_value=mock_async_http):
        remote_res = await search_kubernetes_documentation("OOMKilled")
        assert remote_res["results"][0]["chunk_id"] == "remote-1"
    monkeypatch.setattr("src.config.MCP_SERVER_URL", "")


# ============================================================================
# 5. FastAPI Application & Endpoints (`main.py`)
# ============================================================================

@pytest.mark.asyncio
async def test_fastapi_endpoints_and_formatter():
    formatter = StructuredJsonFormatter()
    try:
        raise ValueError("sample error")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=exc_info,
    )
    record.audit_payload = {"event_type": "TEST_EVENT"}
    formatted = json.loads(formatter.format(record))
    assert formatted["event_type"] == "TEST_EVENT"
    assert "ValueError" in formatted["exception"]

    async with lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r_root = await client.get("/")
            assert r_root.status_code == 200
            assert r_root.json()["status"] == "online"

            r_health = await client.get("/healthz")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "healthy"

            r_mcp_status = await client.get("/api/v1/mcp/status")
            assert r_mcp_status.status_code == 200
            assert r_mcp_status.json()["server_name"] == "mcp-k8s-docs-server"

            with patch("main.mcp_search_kubernetes_documentation", new=AsyncMock(return_value={"status": "success", "results": []})):
                r_search = await client.get("/api/v1/mcp/search?query=OOMKilled")
                assert r_search.status_code == 200
                assert r_search.json()["status"] == "success"

            with patch("main.record_feedback_to_firestore", new=AsyncMock(return_value={"persisted": True, "sink": "firestore"})):
                r_fb = await client.post(
                    "/api/v1/feedback",
                    json={"incident_id": "inc-100", "rating": "thumbs_up"},
                )
                assert r_fb.status_code == 200
                assert r_fb.json()["success"] is True

            # Test /api/v1/diagnose success and error branches with mocked run_agent_pipeline
            mock_state = IncidentState(
                incident_id="inc-ok",
                raw_logs="OOMKilled pod",
                planner_checklist=["1. Check pod"],
                troubleshooting_plan=TroubleshootingPlan(
                    problem_summary="OOMKilled",
                    error_type="OOMKilled",
                    steps=[
                        KubectlCommand(
                            step_number=1,
                            title="Describe",
                            command="kubectl describe pod app",
                            explanation="Inspect pod",
                            danger_level="LOW",
                        )
                    ],
                    source_citations=["https://kubernetes.io/docs/"],
                ),
                status="COMPLETED",
                metadata={"prompt_tokens": 50, "completion_tokens": 25},
            )
            with patch("main.run_agent_pipeline", new=AsyncMock(return_value=mock_state)):
                r_diag = await client.post("/api/v1/diagnose", json={"raw_logs": "OOMKilled pod"})
                assert r_diag.status_code == 200
                assert r_diag.json()["success"] is True

            with patch("main.run_agent_pipeline", new=AsyncMock(side_effect=RuntimeError("Simulated LLM outage"))):
                r_err = await client.post("/api/v1/diagnose", json={"raw_logs": "OOMKilled pod"})
                assert r_err.status_code == 200
                assert r_err.json()["success"] is False
                assert "Simulated LLM outage" in r_err.json()["error"]
