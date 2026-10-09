"""Observability Sinks for BigQuery Token Metrics and Firestore User Feedback.

Implements the Observability specification in design.md:
- OpenTelemetry (OTEL) traces to Cloud Trace (configured in main.py)
- Token & latency metrics emitted as structured JSON to stdout (`event_type="TOKEN_METRICS"`)
  and routed out-of-process to BigQuery (`k8s_copilot_telemetry`) via Cloud Logging Sink
- User feedback persisted via a module-level singleton `firestore.AsyncClient` (`copilot_feedback` collection)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.auth import get_gcp_credentials
from src.config import PROJECT_ID, BQ_DATASET, BQ_TABLE, FIRESTORE_COLLECTION

logger = logging.getLogger("k8s_copilot_telemetry")

# Module-level singleton for native async Firestore client
_firestore_async_client: Optional[Any] = None


def _sinks_enabled() -> bool:
    """Return True when running on Cloud Run (K_SERVICE) or when ENABLE_GCP_SINKS=true."""
    return bool(os.getenv("K_SERVICE")) or os.getenv("ENABLE_GCP_SINKS", "").lower() == "true"


def _get_firestore_async_client() -> Any:
    """Lazily initialize and return the singleton firestore.AsyncClient."""
    global _firestore_async_client
    if _firestore_async_client is None:
        from google.cloud import firestore  # type: ignore

        creds, project = get_gcp_credentials(project_id=PROJECT_ID)
        _firestore_async_client = firestore.AsyncClient(
            project=project or PROJECT_ID,
            credentials=creds,
        )
    return _firestore_async_client


def record_token_metrics_to_bigquery(
    incident_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    checklist_steps: int,
    validated_commands: int,
    cached_tokens: int = 0,
    latency_ms: float = 0.0,
    planner_latency_ms: float = 0.0,
    executor_latency_ms: float = 0.0,
    error_type: Optional[str] = None,
    cluster_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit token, cost, & latency metrics as structured JSON to stdout for the Cloud Logging -> BigQuery Sink.

    StructuredJsonFormatter formats `audit_payload` as top-level JSON fields and attaches
    OpenTelemetry `trace_id` and `span_id` with zero network I/O overhead.
    """
    # Vertex AI Gemini 2.5 Pro pricing per 1M tokens:
    # Uncached Prompt: $1.25 / 1M | Cached Prompt: $0.3125 / 1M | Completion: $10.00 / 1M
    uncached_prompt_tokens = max(0, prompt_tokens - cached_tokens)
    estimated_cost_usd = round(
        (uncached_prompt_tokens * 1.25 + cached_tokens * 0.3125 + completion_tokens * 10.0) / 1_000_000,
        6,
    )

    row = {
        "event_type": "TOKEN_METRICS",
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": max(prompt_tokens, uncached_prompt_tokens + cached_tokens) + completion_tokens,
        "estimated_cost_usd": estimated_cost_usd,
        "latency_ms": round(float(latency_ms), 2),
        "planner_latency_ms": round(float(planner_latency_ms), 2),
        "executor_latency_ms": round(float(executor_latency_ms), 2),
        "checklist_steps": checklist_steps,
        "validated_commands": validated_commands,
        "error_type": error_type or "GeneralClusterAnomaly",
        "cluster_context": cluster_context or "unknown",
    }

    logger.info(
        f"[{incident_id}] Emitted token and latency telemetry metrics.",
        extra={"audit_payload": row},
    )
    return {
        "sink": "cloud_logging_bigquery_sink",
        "dataset": f"{PROJECT_ID}.{BQ_DATASET}",
        "persisted": True,
        "row": row,
    }



async def record_feedback_to_firestore(
    incident_id: str,
    rating: Optional[str] = None,
    comment: Optional[str] = None,
    user_id: Optional[str] = None,
    copied_command: Optional[str] = None,
    step_number: Optional[int] = None,
    session_duration_sec: Optional[float] = None,
) -> Dict[str, Any]:
    """Persist SRE user feedback (thumbs up/down, comments, copied commands, and session duration) to Firestore (`copilot_feedback`).

    Uses `incident_id` as the Firestore document ID with `merge=True` so rating changes
    overwrite `rating` in-place while `copied_commands` appends via `ArrayUnion`.
    """
    doc_data: Dict[str, Any] = {
        "incident_id": incident_id,
        "user_id": user_id or "anonymous-sre",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if rating is not None:
        doc_data["rating"] = rating
    if comment is not None:
        doc_data["comment"] = comment
    if session_duration_sec is not None:
        doc_data["session_duration_sec"] = round(float(session_duration_sec), 2)

    copied_entry = None
    if copied_command:
        copied_entry = {
            "step_number": step_number,
            "command": copied_command,
        }

    log_payload = {
        "event_type": "USER_FEEDBACK",
        **doc_data,
        **({"copied_command_entry": copied_entry} if copied_entry else {}),
    }

    if not _sinks_enabled():
        logger.info(
            f"[{incident_id}] Recorded user feedback (local structured log).",
            extra={"audit_payload": log_payload},
        )
        return {"sink": "structured_log", "persisted": True, "document_id": incident_id, "document": log_payload}

    try:
        from google.cloud import firestore  # type: ignore

        db = _get_firestore_async_client()
        doc_ref = db.collection(FIRESTORE_COLLECTION).document(incident_id)
        firestore_payload = dict(doc_data)
        if copied_entry:
            firestore_payload["copied_commands"] = firestore.ArrayUnion([copied_entry])
            firestore_payload["copy_click_count"] = firestore.Increment(1)

        await doc_ref.set(firestore_payload, merge=True)
        logger.info(
            f"[{incident_id}] Persisted feedback to Firestore ({FIRESTORE_COLLECTION}/{incident_id})",
            extra={"audit_payload": {"document_id": incident_id, **log_payload}},
        )
        return {
            "sink": "firestore",
            "persisted": True,
            "collection": FIRESTORE_COLLECTION,
            "document_id": incident_id,
            "document": log_payload,
        }
    except Exception as exc:
        logger.warning(f"Firestore feedback sink fallback for {incident_id}: {exc}")
        return {"sink": "structured_log_fallback", "persisted": True, "document_id": incident_id, "document": log_payload}



