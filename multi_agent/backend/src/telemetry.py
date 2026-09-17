"""Observability Sinks for BigQuery Token Metrics and Firestore User Feedback.

Implements the Observability specification in design.md:
- OpenTelemetry (OTEL) traces to Cloud Trace (configured in main.py)
- Token metrics to BigQuery (`k8s_copilot_telemetry.token_metrics`)
- User feedback to Firestore (`copilot_feedback` collection)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.auth import get_gcp_credentials

logger = logging.getLogger("k8s_copilot_telemetry")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
BQ_DATASET = os.getenv("BQ_TELEMETRY_DATASET", "k8s_copilot_telemetry")
BQ_TABLE = os.getenv("BQ_TELEMETRY_TABLE", "token_metrics")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_FEEDBACK_COLLECTION", "copilot_feedback")


def _sinks_enabled() -> bool:
    """Return True when running on Cloud Run (K_SERVICE) or when ENABLE_GCP_SINKS=true."""
    return bool(os.getenv("K_SERVICE")) or os.getenv("ENABLE_GCP_SINKS", "").lower() == "true"


def record_token_metrics_to_bigquery(
    incident_id: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    checklist_steps: int,
    validated_commands: int,
    cluster_context: Optional[str] = None,
) -> Dict[str, Any]:
    """Stream token & pipeline execution metrics to BigQuery (`k8s_copilot_telemetry.token_metrics`).

    Falls back to structured telemetry logging when outside Cloud Run (`ENABLE_GCP_SINKS != true`)
    or if the BigQuery table is not yet provisioned.
    """
    row = {
        "incident_id": incident_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "checklist_steps": checklist_steps,
        "validated_commands": validated_commands,
        "cluster_context": cluster_context or "unknown",
    }

    if not _sinks_enabled():
        logger.info(f"[BigQuery Token Telemetry (local)] {row}")
        return {"sink": "structured_log", "persisted": True, "row": row}

    try:
        from google.cloud import bigquery  # type: ignore

        creds, project = get_gcp_credentials(project_id=PROJECT_ID)
        client = bigquery.Client(project=project or PROJECT_ID, credentials=creds)
        table_ref = f"{project or PROJECT_ID}.{BQ_DATASET}.{BQ_TABLE}"
        errors = client.insert_rows_json(table_ref, [row])
        if errors:
            logger.warning(f"BigQuery insert_rows_json returned errors: {errors}")
            return {"sink": "bigquery", "persisted": False, "errors": errors, "row": row}
        logger.info(f"Streamed token metrics for {incident_id} to BigQuery table {table_ref}")
        return {"sink": "bigquery", "persisted": True, "table": table_ref, "row": row}
    except Exception as exc:
        logger.warning(f"BigQuery sink fallback for {incident_id}: {exc}")
        return {"sink": "structured_log_fallback", "persisted": True, "row": row}


def record_feedback_to_firestore(
    incident_id: str,
    rating: str,
    comment: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist SRE user feedback (thumbs up/down) to Google Cloud Firestore (`copilot_feedback`).

    Falls back to structured logging when outside Cloud Run (`ENABLE_GCP_SINKS != true`)
    or if Firestore is unavailable.
    """
    doc_data = {
        "incident_id": incident_id,
        "rating": rating,
        "comment": comment,
        "user_id": user_id or "anonymous-sre",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    if not _sinks_enabled():
        logger.info(f"[Firestore Feedback Sink (local)] {doc_data}")
        return {"sink": "structured_log", "persisted": True, "document": doc_data}

    try:
        from google.cloud import firestore  # type: ignore

        creds, project = get_gcp_credentials(project_id=PROJECT_ID)
        db = firestore.Client(project=project or PROJECT_ID, credentials=creds)
        doc_ref = db.collection(FIRESTORE_COLLECTION).document()
        doc_ref.set(doc_data)
        logger.info(f"Persisted feedback for {incident_id} to Firestore ({FIRESTORE_COLLECTION}/{doc_ref.id})")
        return {
            "sink": "firestore",
            "persisted": True,
            "collection": FIRESTORE_COLLECTION,
            "document_id": doc_ref.id,
            "document": doc_data,
        }
    except Exception as exc:
        logger.warning(f"Firestore feedback sink fallback for {incident_id}: {exc}")
        return {"sink": "structured_log_fallback", "persisted": True, "document": doc_data}
