"""FastAPI Application for the Kubernetes Troubleshooting Copilot Backend.

Architecture:
- Decoupled Planner-Executor Multi-Agent Pipeline.
- Deterministic Safety Guardian Command Interception.
- OpenTelemetry Observability (Cloud Trace / Latency / Token Telemetry).
- SRE Feedback Collection.
"""

import os
import sys
import uuid
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.models import (
    DiagnoseRequest,
    DiagnoseResponse,
    IncidentState,
    TroubleshootingPlan,
    KubectlCommand,
    FeedbackRequest,
    FeedbackResponse,
)
from src.agents import PlannerAgent, ExecutorAgent
from src.guardrails import SafetyGuardian

# --- OpenTelemetry Setup ---
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("k8s_copilot_api")

# Configure Tracer Provider
tracer_provider = TracerProvider()
try:
    from opentelemetry.exporter.gcp_trace import CloudTraceSpanExporter
    cloud_trace_exporter = CloudTraceSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(cloud_trace_exporter))
    logger.info("OpenTelemetry configured with Google Cloud Trace exporter.")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to initialize agent singletons on startup."""
    global _planner_agent, _executor_agent
    logger.info("Initializing Kubernetes Troubleshooting Copilot Agents...")
    _planner_agent = PlannerAgent(model_name="gemini-2.5-pro")
    _executor_agent = ExecutorAgent(model_name="gemini-2.5-pro")
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
            # Step 2: Phase 1 - Planner Agent (Root Cause Analysis & Doc Search)
            with tracer.start_as_current_span("planner_phase"):
                logger.info(f"[{incident_id}] Running PlannerAgent...")
                state = await planner.plan(state)
                logger.info(f"[{incident_id}] Planner completed with {len(state.planner_checklist)} steps.")

            # Step 3: Phase 2 - Executor Agent (Structured Command Generation & Safety Interception)
            with tracer.start_as_current_span("executor_phase"):
                logger.info(f"[{incident_id}] Running ExecutorAgent & SafetyGuardian...")
                state = await executor.execute(state)
                logger.info(f"[{incident_id}] Executor completed with {len(state.final_validated_command)} validated commands.")

            # Step 4: Construct Final Troubleshooting Plan
            plan_summary = (
                f"Incident {incident_id} Diagnosis: "
                f"{state.raw_logs[:120]}..." if len(state.raw_logs) > 120 else state.raw_logs
            )

            citations = [
                "https://kubernetes.io/docs/tasks/debug/",
                "https://kubernetes.io/docs/reference/kubectl/",
                "https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/"
            ]

            plan = TroubleshootingPlan(
                problem_summary=plan_summary,
                steps=state.final_validated_command,
                source_citations=citations
            )

            state.status = "COMPLETED"
            logger.info(f"[{incident_id}] Incident diagnosis successfully completed.")

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


@app.post(
    "/api/v1/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    tags=["Telemetry"],
    summary="Record SRE feedback (thumbs up/down) for incident diagnosis."
)
async def submit_feedback(feedback: FeedbackRequest) -> FeedbackResponse:
    """Collect SRE review feedback for telemetry and model evaluation."""
    logger.info(f"Received feedback for incident {feedback.incident_id}: rating={feedback.rating}, user={feedback.user_id}")
    
    # Store feedback in structured log / Firestore
    # In production, writes to google-cloud-firestore collection 'copilot_feedback'
    return FeedbackResponse(
        success=True,
        message=f"Feedback for incident {feedback.incident_id} recorded successfully."
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
