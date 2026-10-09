"""Authentication, SPIFFE Workload Identity & Secret Manager Module (`src.auth`).

Fulfils the Security & Authentication requirements:
1. SPIFFE-based identities in the Argolis Sandbox (`spiffe://<trust-domain>/...`)
   via Google Cloud Workload Identity Federation / `google.auth` to access GCP APIs
   (Vertex AI Search, Gemini, Cloud Trace).
2. Google Cloud Secret Manager (`google.cloud.secretmanager`) to manage API keys
   for external services and telemetry collectors with in-memory caching.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import google.auth
from google.auth import identity_pool
from google.auth.credentials import Credentials
from google.cloud import secretmanager

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from src.config import (
    PROJECT_ID,
    DEFAULT_TRUST_DOMAIN,
    DEFAULT_SPIFFE_ID,
    MCP_SPIFFE_ID,
    DEFAULT_SVID_TOKEN_PATH,
    MCP_SERVER_URL,
    ALLOWED_AGENT_SA_EMAIL,
    REQUIRE_END_USER_AUTH,
    REQUIRE_AGENT_AUTH,
)

logger = logging.getLogger("k8s_auth")

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
        "mcp_spiffe_id": MCP_SPIFFE_ID,
        "trust_domain": DEFAULT_TRUST_DOMAIN,
        "mcp_server_mode": "remote_microservice" if MCP_SERVER_URL else "in_process",
        "mcp_server_url": MCP_SERVER_URL or "in-process",
        "require_end_user_auth": REQUIRE_END_USER_AUTH,
        "require_agent_auth": REQUIRE_AGENT_AUTH,
        "secret_manager_enabled": True,
    }


# ============================================================================
# Multi-Hop Authentication & Authorization (End User -> Agent -> MCP Server)
# ============================================================================

def verify_end_user_identity(
    authorization: Optional[str] = None,
    iap_jwt: Optional[str] = None,
) -> Dict[str, Any]:
    """Hop 1: Verifies End-User identity from Cloud IAP (`X-Goog-IAP-JWT-Assertion`) or Bearer OIDC token.

    When `REQUIRE_END_USER_AUTH=true`, raises PermissionError if no valid token is supplied.
    In local sandbox development (`REQUIRE_END_USER_AUTH=false`), returns a verified or anonymous SRE context.
    """
    raw_token = None
    auth_source = "anonymous_sandbox"

    if iap_jwt:
        raw_token = iap_jwt.strip()
        auth_source = "cloud_iap_jwt"
    elif authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
        auth_source = "oidc_bearer_token"

    if raw_token:
        try:
            claims = google_id_token.verify_oauth2_token(raw_token, GoogleAuthRequest())
            return {
                "authenticated": True,
                "source": auth_source,
                "email": claims.get("email", claims.get("sub", "unknown")),
                "sub": claims.get("sub"),
            }
        except Exception as exc:
            if REQUIRE_END_USER_AUTH:
                raise PermissionError(f"Invalid End-User OIDC/IAP token: {exc}") from exc
            logger.warning(f"End-user token validation failed in permissive mode ({exc}).")

    if REQUIRE_END_USER_AUTH:
        raise PermissionError("Missing End-User authentication token (Authorization Bearer or X-Goog-IAP-JWT-Assertion).")

    return {
        "authenticated": False,
        "source": auth_source,
        "email": "sre-sandbox@cloudnative-ops.internal",
        "sub": "sandbox-user",
    }


def fetch_agent_id_token(target_audience: str) -> Optional[str]:
    """Hop 2: Fetches a Google-signed OIDC ID token or SPIFFE JWT-SVID for the Agent (`k8s-copilot-sa`)
    to authenticate outbound calls to the standalone `mcp-k8s-docs-server` microservice.
    """
    svid_path = Path(DEFAULT_SVID_TOKEN_PATH)
    if svid_path.exists():
        try:
            return svid_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.debug(f"Could not read local SPIFFE SVID token: {exc}")

    try:
        return google_id_token.fetch_id_token(GoogleAuthRequest(), target_audience)
    except Exception as exc:
        logger.debug(f"Could not fetch Cloud Run OIDC ID token for {target_audience}: {exc}")
        return None


def verify_agent_gateway_token(
    authorization: Optional[str] = None,
    spiffe_id_header: Optional[str] = None,
    expected_audience: Optional[str] = None,
) -> Dict[str, Any]:
    """Hop 3 (Agent Gateway on MCP Server): Verifies that an incoming request to `mcp-k8s-docs-server`
    originates from the authorized Agent Service Account (`k8s-copilot-sa`) and SPIFFE ID.
    """
    caller_spiffe_id = spiffe_id_header or DEFAULT_SPIFFE_ID
    if not authorization or not authorization.lower().startswith("bearer "):
        if REQUIRE_AGENT_AUTH:
            raise PermissionError("Agent Gateway rejected request: missing Authorization Bearer token.")
        return {"authorized": True, "mode": "in_process_or_permissive", "caller_spiffe_id": caller_spiffe_id}

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = google_id_token.verify_oauth2_token(
            token,
            GoogleAuthRequest(),
            audience=expected_audience,
        )
        caller_email = claims.get("email", "")
        caller_sub = claims.get("sub", "")

        if ALLOWED_AGENT_SA_EMAIL and caller_email and caller_email != ALLOWED_AGENT_SA_EMAIL:
            raise PermissionError(
                f"Agent Gateway rejected caller '{caller_email}': only '{ALLOWED_AGENT_SA_EMAIL}' is authorized."
            )
        if spiffe_id_header and spiffe_id_header != DEFAULT_SPIFFE_ID:
            raise PermissionError(
                f"Agent Gateway rejected SPIFFE ID '{spiffe_id_header}': expected '{DEFAULT_SPIFFE_ID}'."
            )

        return {
            "authorized": True,
            "mode": "verified_oidc_agent_identity",
            "caller_email": caller_email or caller_sub,
            "caller_spiffe_id": caller_spiffe_id,
        }
    except PermissionError:
        raise
    except Exception as exc:
        if REQUIRE_AGENT_AUTH:
            raise PermissionError(f"Agent Gateway token verification failed: {exc}") from exc
        return {"authorized": True, "mode": "permissive_fallback", "caller_spiffe_id": caller_spiffe_id}


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
    """Fetches an API key or telemetry collector token from Google Cloud Secret Manager."""
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
        env_val = os.getenv(default_env_var) if default_env_var else None
        if env_val:
            _secret_cache[cache_key] = env_val
            return env_val
        return os.getenv(secret_id.upper().replace("-", "_"))

