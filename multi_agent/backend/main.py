"""FastAPI Application for the Kubernetes Troubleshooting Copilot Backend.

Architecture:
- Decoupled Planner-Executor Multi-Agent Pipeline.
- Deterministic Safety Guardian Command Interception.
- OpenTelemetry Observability (Cloud Trace / Latency / Token Telemetry).
- SRE Feedback Collection.
"""

import os
import sys
import json
import time
import uuid
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from google.adk.agents import SequentialAgent
from src.models import (
    DiagnoseRequest,
    DiagnoseResponse,
    IncidentState,
    TroubleshootingPlan,
    FeedbackRequest,
    FeedbackResponse,
)
from src.config import PROJECT_ID, DATASTORE_ID, CORS_ORIGINS
from src.agents import (
    DEFAULT_MODEL,
    planner_agent,
    executor_agent,
    root_orchestrator,
    run_agent_pipeline,
)
from src.mcp_server import mcp_server, mcp_search_kubernetes_documentation
from src.telemetry import record_token_metrics_to_bigquery, record_feedback_to_firestore

# --- OpenTelemetry Setup ---
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects with OpenTelemetry trace/span IDs for Cloud Logging."""

    def format(self, record: logging.LogRecord) -> str:
        span_ctx = trace.get_current_span().get_span_context()
        trace_id = f"{span_ctx.trace_id:032x}" if span_ctx and span_ctx.is_valid else None
        span_id = f"{span_ctx.span_id:016x}" if span_ctx and span_ctx.is_valid else None

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }
        if trace_id:
            log_entry["logging.googleapis.com/trace"] = f"projects/{PROJECT_ID}/traces/{trace_id}"
            log_entry["logging.googleapis.com/spanId"] = span_id

        audit_payload = getattr(record, "audit_payload", None)
        if isinstance(audit_payload, dict):
            log_entry.update(audit_payload)

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# Configure Structured JSON Logging
_json_handler = logging.StreamHandler(sys.stdout)
_json_handler.setFormatter(StructuredJsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_json_handler], force=True)
logger = logging.getLogger("k8s_copilot_api")

from src.auth import (
    get_identity_metadata,
    get_secret,
    verify_end_user_identity,
    verify_agent_gateway_token,
)

# Configure Tracer Provider (attaches GCP Cloud Trace exporter on Cloud Run or when ENABLE_CLOUD_TRACE=true)
tracer_provider = TracerProvider()
if os.getenv("K_SERVICE") or os.getenv("ENABLE_CLOUD_TRACE", "").lower() == "true":
    try:
        telemetry_api_key = get_secret(
            "telemetry-collector-api-key",
            default_env_var="TELEMETRY_COLLECTOR_API_KEY",
        )
        from opentelemetry.exporter.gcp_trace import CloudTraceSpanExporter
        cloud_trace_exporter = CloudTraceSpanExporter()
        tracer_provider.add_span_processor(
            BatchSpanProcessor(cloud_trace_exporter, export_timeout_millis=2000)
        )
        logger.info(
            f"OpenTelemetry configured with Google Cloud Trace exporter "
            f"(Secret Manager collector key loaded: {bool(telemetry_api_key)})."
        )
    except Exception as otel_err:
        logger.info(f"Using local OpenTelemetry Tracer: {otel_err}")

trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("k8s_copilot_tracer")


# ============================================================================
# Application Lifespan & Dependency Providers
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for the FastAPI application."""
    logger.info("Initializing Kubernetes Troubleshooting Copilot ADK Agents...")
    yield
    logger.info("Shutting down Kubernetes Troubleshooting Copilot Backend.")


def get_root_orchestrator() -> SequentialAgent:
    """Dependency provider for the native ADK `root_orchestrator` (`SequentialAgent`)."""
    return root_orchestrator


# ============================================================================
# FastAPI Initialization
# ============================================================================

app = FastAPI(
    title="Kubernetes Troubleshooting Copilot API",
    description="Context-grounded, multi-agent platform for Kubernetes anomaly debugging and safe kubectl remediation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Frontend Access
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Mount the MCP Server (`mcp-k8s-docs-server`) SSE transport at /mcp
try:
    app.mount("/mcp", mcp_server.sse_app())
except Exception as mcp_mount_err:
    logger.warning(f"Could not mount MCP SSE transport: {mcp_mount_err}")


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Health"])
async def root():
    """Root metadata endpoint."""
    return {
        "service": "kubernetes-troubleshooting-copilot",
        "status": "online",
        "version": "1.0.0",
        "agents": {
            "orchestrator": root_orchestrator.name,
            "planner": planner_agent.name,
            "executor": executor_agent.name,
            "guardian": "SafetyGuardian (Deterministic Risk Matrix)"
        }
    }


@app.get("/healthz", tags=["Health"])
async def health_check():
    """Liveness probe endpoint for Cloud Run."""
    return {"status": "healthy"}


@app.post(
    "/api/v1/diagnose",
    response_model=DiagnoseResponse,
    status_code=status.HTTP_200_OK,
    tags=["Diagnosis"],
    summary="Diagnose Kubernetes crash logs and generate a validated remediation plan."
)
async def diagnose_incident(
    request: DiagnoseRequest,
    orchestrator: SequentialAgent = Depends(get_root_orchestrator),
    authorization: Optional[str] = Header(default=None),
    x_goog_iap_jwt_assertion: Optional[str] = Header(default=None),
) -> DiagnoseResponse:
    """End-to-End SRE Incident Diagnosis Pipeline using native ADK `root_orchestrator` (`SequentialAgent`)."""
    try:
        user_ctx = verify_end_user_identity(
            authorization=authorization,
            iap_jwt=x_goog_iap_jwt_assertion,
        )
    except PermissionError as auth_err:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(auth_err))

    incident_id = request.incident_id or f"inc-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    logger.info(f"Starting diagnosis pipeline for incident: {incident_id} (user={user_ctx.get('email')})")

    with tracer.start_as_current_span("diagnose_incident") as span:
        span.set_attribute("incident.id", incident_id)
        span.set_attribute("cluster.context", request.cluster_context or "unknown")
        span.set_attribute("end_user.email", user_ctx.get("email", "unknown"))

        # Step 1: Initialize State
        state = IncidentState(
            incident_id=incident_id,
            raw_logs=request.raw_logs,
            cluster_context=request.cluster_context,
            status="INITIALIZED",
            metadata={"user_principal": user_ctx.get("email"), "auth_source": user_ctx.get("source")},
        )

        try:
            # Step 2: Execute native ADK SequentialAgent (`planner_agent` -> `executor_agent`) via ADK Runner
            with tracer.start_as_current_span("root_orchestrator_phase"):
                logger.info(f"[{incident_id}] Running ADK root_orchestrator (SequentialAgent)...")
                state = await run_agent_pipeline(state, agent=orchestrator)

            # Step 3: Finalize Troubleshooting Plan & Error Classification
            plan = state.troubleshooting_plan or TroubleshootingPlan(
                problem_summary=state.raw_logs[:120],
                steps=[],
                source_citations=state.source_citations or [],
            )
            error_type = plan.error_type or "GeneralClusterAnomaly"
            state.metadata["error_type"] = error_type
            logger.info(
                f"[{incident_id}] root_orchestrator completed (status={state.status}, "
                f"checklist={len(state.planner_checklist or [])}, "
                f"validated_commands={len(plan.steps)})."
            )

            # Step 4: Emit token, latency, & error_type metrics via stdout JSON for the Cloud Logging -> BigQuery Sink
            elapsed_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            state.metadata.setdefault("latency_ms", elapsed_latency_ms)
            telemetry_result = record_token_metrics_to_bigquery(
                incident_id=incident_id,
                model_name=DEFAULT_MODEL,
                prompt_tokens=state.metadata.get("prompt_tokens", 0),
                cached_tokens=state.metadata.get("cached_tokens", 0),
                completion_tokens=state.metadata.get("completion_tokens", 0),
                latency_ms=state.metadata.get("latency_ms", elapsed_latency_ms),
                planner_latency_ms=state.metadata.get("planner_latency_ms", 0.0),
                executor_latency_ms=state.metadata.get("executor_latency_ms", 0.0),
                checklist_steps=len(state.planner_checklist or []),
                validated_commands=len(plan.steps),
                error_type=error_type,
                cluster_context=state.cluster_context,
            )
            state.metadata["telemetry_sink"] = telemetry_result.get("sink", "cloud_logging_bigquery_sink")

            # Step 5: Emit immutable Audit Trail log capturing exact SRE query and generated command responses
            logger.info(
                f"[{incident_id}] Incident diagnosis completed and audited.",
                extra={
                    "audit_payload": {
                        "event_type": "AUDIT_TRAIL",
                        "incident_id": incident_id,
                        "cluster_context": state.cluster_context or "unknown",
                        "sre_query": request.raw_logs,
                        "generated_commands": [
                            {
                                "step_number": s.step_number,
                                "title": s.title,
                                "command": s.command,
                                "danger_level": s.danger_level,
                                "alternative_command": s.alternative_command,
                            }
                            for s in (plan.steps or [])
                        ],
                        "source_citations": plan.source_citations,
                    }
                },
            )

            return DiagnoseResponse(
                success=True,
                plan=plan,
                state=state,
                error=None
            )

        except Exception as exc:
            logger.error(f"[{incident_id}] Error in diagnosis pipeline: {exc}", exc_info=True)
            state.status = "ERROR"
            return DiagnoseResponse(
                success=False,
                plan=None,
                state=state,
                error=f"Diagnosis pipeline error: {str(exc)}"
            )


@app.get("/api/v1/mcp/status", tags=["MCP Server"])
async def mcp_server_status():
    """Return status, SPIFFE identity metadata, and registered tools of the mcp-k8s-docs-server."""
    tools = await mcp_server.list_tools()
    return {
        "server_name": mcp_server.name,
        "datastore_id": DATASTORE_ID,
        "transports": ["stdio", "sse"],
        "sse_endpoint": "/mcp/sse",
        "auth": get_identity_metadata(),
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ],
    }


@app.get("/api/v1/mcp/search", tags=["MCP Server"])
async def mcp_server_search(
    query: str,
    top_k: int = 3,
    authorization: Optional[str] = Header(default=None),
    x_agent_spiffe_id: Optional[str] = Header(default=None),
):
    """Query the mcp-k8s-docs-server directly (enforces Agent Gateway caller verification)."""
    try:
        verify_agent_gateway_token(
            authorization=authorization,
            spiffe_id_header=x_agent_spiffe_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return await mcp_search_kubernetes_documentation(query=query, top_k=top_k)


@app.post(
    "/api/v1/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    tags=["Telemetry"],
    summary="Record SRE feedback (thumbs up/down, comments, and copy-to-clipboard actions) for incident diagnosis."
)
async def submit_feedback(feedback: FeedbackRequest) -> FeedbackResponse:
    """Collect SRE review feedback and command copy actions in Firestore (`copilot_feedback`)."""
    logger.info(
        f"Received feedback for incident {feedback.incident_id}: "
        f"rating={feedback.rating}, copied_command={bool(feedback.copied_command)}, user={feedback.user_id}"
    )

    sink_res = await record_feedback_to_firestore(
        incident_id=feedback.incident_id,
        rating=feedback.rating,
        comment=feedback.comments,
        user_id=feedback.user_id,
        copied_command=feedback.copied_command,
        step_number=feedback.step_number,
        session_duration_sec=feedback.session_duration_sec,
    )
    return FeedbackResponse(
        success=bool(sink_res.get("persisted", True)),
        message=f"Feedback for incident {feedback.incident_id} recorded successfully ({sink_res.get('sink', 'firestore')})."
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
