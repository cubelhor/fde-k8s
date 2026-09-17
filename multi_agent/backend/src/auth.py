"""Authentication, SPIFFE Workload Identity & Secret Manager Module (`src.auth`).

Fulfils the Security & Authentication requirements:
1. SPIFFE-based identities in the Argolis Sandbox (`spiffe://<trust-domain>/...`)
   via Google Cloud Workload Identity Federation / `google.auth` to access GCP APIs
   (Vertex AI Search, Gemini, Cloud Trace).
2. Google Cloud Secret Manager (`google.cloud.secretmanager`) to manage API keys
   for external services and telemetry collectors with in-memory caching.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import google.auth
from google.auth import identity_pool
from google.auth.credentials import Credentials
from google.cloud import secretmanager

logger = logging.getLogger("k8s_auth")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
DEFAULT_TRUST_DOMAIN = os.getenv("SPIFFE_TRUST_DOMAIN", f"{PROJECT_ID}.svc.id.goog")
DEFAULT_SPIFFE_ID = os.getenv(
    "SPIFFE_ID",
    f"spiffe://{DEFAULT_TRUST_DOMAIN}/ns/default/sa/k8s-copilot-backend-sa",
)
DEFAULT_SVID_TOKEN_PATH = os.getenv(
    "SPIFFE_SVID_TOKEN_PATH",
    "/var/run/secrets/spiffe.io/svid.jwt",
)

# Module-level singletons for credentials, Secret Manager client, and cached secrets
_cached_credentials: Optional[Credentials] = None
_identity_mode: str = "uninitialized"
_secret_client: Optional[secretmanager.SecretManagerServiceClient] = None
_secret_cache: Dict[str, str] = {}


def get_gcp_credentials(project_id: str = PROJECT_ID) -> Tuple[Credentials, str]:
    """Resolves GCP credentials prioritizing SPIFFE Workload Identity in the Argolis Sandbox.

    Resolution order:
    1. Explicit SPIFFE JWT-SVID / Workload Identity Pool configuration (`SPIFFE_WIP_AUDIENCE`
       and `SPIFFE_SVID_TOKEN_PATH`) using `google.auth.identity_pool.Credentials`.
    2. Standard `google.auth.default()` (supports GKE/Cloud Run SPIFFE Workload Identity
       Metadata Server and local developer ADC).
    """
    global _cached_credentials, _identity_mode
    if _cached_credentials is not None:
        return _cached_credentials, _identity_mode

    wip_audience = os.getenv("SPIFFE_WIP_AUDIENCE")
    svid_path = Path(DEFAULT_SVID_TOKEN_PATH)

    if wip_audience and svid_path.exists():
        try:
            config_info = {
                "type": "external_account",
                "audience": wip_audience,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "token_url": "https://sts.googleapis.com/v1/token",
                "credential_source": {"file": str(svid_path)},
            }
            _cached_credentials = identity_pool.Credentials.from_info(
                config_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
                quota_project_id=project_id,
            )
            _identity_mode = "spiffe_workload_identity_federation"
            logger.info(f"Authenticated via SPIFFE Workload Identity ({DEFAULT_SPIFFE_ID}).")
            return _cached_credentials, _identity_mode
        except Exception as exc:
            logger.warning(f"SPIFFE Workload Identity Pool initialization failed ({exc}); falling back to ADC.")

    # Standard google.auth.default (handles GKE/Cloud Run SPIFFE Metadata Server & local ADC)
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
        quota_project_id=project_id,
    )
    _cached_credentials = creds
    _identity_mode = (
        "spiffe_gke_cloudrun_workload_identity"
        if os.getenv("K_SERVICE") or os.getenv("KUBERNETES_SERVICE_HOST")
        else "application_default_credentials"
    )
    return _cached_credentials, _identity_mode


def get_identity_metadata() -> Dict[str, Any]:
    """Returns diagnostic metadata about the active SPIFFE / GCP authentication identity."""
    try:
        _, mode = get_gcp_credentials()
    except Exception:
        mode = "offline_fallback"

    return {
        "project_id": PROJECT_ID,
        "identity_mode": mode,
        "spiffe_id": DEFAULT_SPIFFE_ID,
        "trust_domain": DEFAULT_TRUST_DOMAIN,
        "secret_manager_enabled": True,
    }


def _get_secret_manager_client() -> secretmanager.SecretManagerServiceClient:
    """Returns a persistent SecretManagerServiceClient singleton."""
    global _secret_client
    if _secret_client is None:
        creds, _ = get_gcp_credentials()
        _secret_client = secretmanager.SecretManagerServiceClient(credentials=creds)
    return _secret_client


def get_secret(
    secret_id: str,
    version_id: str = "latest",
    project_id: str = PROJECT_ID,
    default_env_var: Optional[str] = None,
) -> Optional[str]:
    """Fetches an API key or telemetry collector token from Google Cloud Secret Manager.

    Args:
        secret_id: Name of the secret in GCP Secret Manager (e.g. 'telemetry-collector-api-key').
        version_id: Version of the secret (defaults to 'latest').
        project_id: GCP Project ID hosting Secret Manager.
        default_env_var: Optional fallback environment variable name for local development.

    Returns:
        The decoded secret payload string, or fallback value if offline.
    """
    cache_key = f"{project_id}/{secret_id}/{version_id}"
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    try:
        client = _get_secret_manager_client()
        secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": secret_name}, timeout=2.0)
        payload = response.payload.data.decode("utf-8").strip()
        _secret_cache[cache_key] = payload
        logger.info(f"Loaded secret '{secret_id}' from Google Cloud Secret Manager.")
        return payload
    except Exception as exc:
        logger.debug(f"Secret Manager lookup for '{secret_id}' fell back to env ({exc}).")
        if default_env_var and os.getenv(default_env_var):
            val = os.getenv(default_env_var)
            _secret_cache[cache_key] = val
            return val
        return os.getenv(secret_id.upper().replace("-", "_"))
