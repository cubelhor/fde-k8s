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

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models import (
    DiagnoseRequest,
    DiagnoseResponse,
    IncidentState,
    TroubleshootingPlan,
    FeedbackRequest,
    FeedbackResponse,
)
from src.agents import PlannerAgent, ExecutorAgent, RootOrchestrator

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
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        }
        if trace_id:
            log_entry["logging.googleapis.com/trace"] = f"projects/{project_id}/traces/{trace_id}"
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

from src.auth import get_identity_metadata, get_secret

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

# Global Agent Instances
_planner_agent: Optional[PlannerAgent] = None
_executor_agent: Optional[ExecutorAgent] = None
_root_orchestrator: Optional[RootOrchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to initialize agent singletons on startup."""
    global _planner_agent, _executor_agent, _root_orchestrator
    logger.info("Initializing Kubernetes Troubleshooting Copilot Agents...")
    _planner_agent = PlannerAgent(model_name="gemini-2.5-pro")
    _executor_agent = ExecutorAgent(model_name="gemini-2.5-pro")
    _root_orchestrator = RootOrchestrator(planner=_planner_agent, executor=_executor_agent)
    yield
    logger.info("Shutting down Kubernetes Troubleshooting Copilot Backend.")


def get_planner_agent() -> PlannerAgent:
    """Dependency provider for the PlannerAgent."""
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = PlannerAgent(model_name="gemini-2.5-pro")
    return _planner_agent


def get_executor_agent() -> ExecutorAgent:
    """Dependency provider for the ExecutorAgent."""
    global _executor_agent
    if _executor_agent is None:
        _executor_agent = ExecutorAgent(model_name="gemini-2.5-pro")
    return _executor_agent


def get_root_orchestrator(planner: PlannerAgent, executor: ExecutorAgent) -> RootOrchestrator:
    """Return singleton RootOrchestrator when default agents are used, or wrap overridden test dependencies."""
    global _root_orchestrator, _planner_agent, _executor_agent
    if _root_orchestrator is not None and planner is _planner_agent and executor is _executor_agent:
        return _root_orchestrator
    return RootOrchestrator(planner=planner, executor=executor)


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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auto-instrument FastAPI with OpenTelemetry
FastAPIInstrumentor.instrument_app(app)

# Mount the MCP Server (`mcp-k8s-docs-server`) SSE transport at /mcp
try:
    from src.mcp_server import mcp_server as _k8s_mcp_server
    app.mount("/mcp", _k8s_mcp_server.sse_app())
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
            "planner": "PlannerAgent (ADK + Vertex AI Search)",
            "executor": "ExecutorAgent (Gemini 2.5 Pro Structured Outputs)",
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
    planner: PlannerAgent = Depends(get_planner_agent),
    executor: ExecutorAgent = Depends(get_executor_agent),
) -> DiagnoseResponse:
    """End-to-End SRE Incident Diagnosis Pipeline.
    
    Workflow:
    1. Initialize IncidentState with raw crash logs and cluster context.
    2. Phase 1 (Planning): PlannerAgent uses ADK Runner and Vertex AI Search to research and construct diagnostic checklist.
    3. Phase 2 (Execution): ExecutorAgent translates checklist into structured KubectlCommand steps.
    4. Phase 3 (Safety Interception): SafetyGuardian inspects every command against LOW/MEDIUM/HIGH risk matrix.
    5. Returns finalized TroubleshootingPlan and full IncidentState trajectory.
    """
    incident_id = request.incident_id or f"inc-{uuid.uuid4().hex[:8]}"
    start_time = time.perf_counter()
    logger.info(f"Starting diagnosis pipeline for incident: {incident_id}")

    with tracer.start_as_current_span("diagnose_incident") as span:
        span.set_attribute("incident.id", incident_id)
        span.set_attribute("cluster.context", request.cluster_context or "unknown")

        # Step 1: Initialize State
        state = IncidentState(
            incident_id=incident_id,
            raw_logs=request.raw_logs,
            cluster_context=request.cluster_context,
            status="INITIALIZED",
        )

        try:
            # Step 2: Delegate multi-agent execution to RootOrchestrator (SequentialAgent: PlannerAgent -> ExecutorAgent)
            with tracer.start_as_current_span("root_orchestrator_phase"):
                logger.info(f"[{incident_id}] Running RootOrchestrator (SequentialAgent)...")
                orchestrator = get_root_orchestrator(planner=planner, executor=executor)
                state = await orchestrator.orchestrate(state)
                logger.info(
                    f"[{incident_id}] RootOrchestrator completed (status={state.status}, "
                    f"checklist={len(state.planner_checklist or [])}, "
                    f"validated_commands={len(state.final_validated_command or [])})."
                )

            # Step 3: Construct Final Troubleshooting Plan from MCP / Vertex AI Search & Executor output
            plan_summary = state.metadata.get("problem_summary") or (
                f"Incident {incident_id} Diagnosis: "
                f"{state.raw_logs[:120]}..." if len(state.raw_logs) > 120 else state.raw_logs
            )

            citations = state.source_citations if state.source_citations else [
                "https://kubernetes.io/docs/tasks/debug/",
                "https://kubernetes.io/docs/reference/kubectl/",
                "https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/"
            ]

            from src.telemetry import record_token_metrics_to_bigquery, classify_cluster_error_type
            error_type = state.metadata.get("error_type") or classify_cluster_error_type(state.raw_logs)
            state.metadata["error_type"] = error_type

            plan = TroubleshootingPlan(
                problem_summary=plan_summary,
                error_type=error_type,
                steps=state.final_validated_command,
                source_citations=citations
            )

            # Step 4: Emit token, latency, & error_type metrics via stdout JSON for the Cloud Logging -> BigQuery Sink
            elapsed_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
            est_prompt_tokens = max(1, len(state.raw_logs or "") // 4)
            est_completion_tokens = max(
                1,
                sum(len(s.command) + len(s.explanation) for s in (state.final_validated_command or [])) // 4,
            )
            telemetry_result = record_token_metrics_to_bigquery(
                incident_id=incident_id,
                model_name=getattr(planner, "model_name", "gemini-2.5-pro"),
                prompt_tokens=state.metadata.get("prompt_tokens", est_prompt_tokens),
                cached_tokens=state.metadata.get("cached_tokens", 0),
                completion_tokens=state.metadata.get("completion_tokens", est_completion_tokens),
                latency_ms=state.metadata.get("latency_ms", elapsed_latency_ms),
                checklist_steps=len(state.planner_checklist or []),
                validated_commands=len(state.final_validated_command or []),
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
                        "source_citations": citations,
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
    from src.mcp_server import mcp_server, DATASTORE_ID
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
async def mcp_server_search(query: str, top_k: int = 3):
    """Query the mcp-k8s-docs-server directly to inspect retrieved Vertex AI Search chunks."""
    from src.mcp_server import mcp_search_kubernetes_documentation
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

    from src.telemetry import record_feedback_to_firestore
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
