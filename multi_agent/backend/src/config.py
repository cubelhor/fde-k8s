"""Centralized Environment Configuration for the Kubernetes Troubleshooting Copilot Backend.

In Cloud Run production, these variables are injected by Terraform (`multi_agent/infra/main.tf`).
In local development and CI, safe fallback defaults are provided here in a single module.
"""

import os

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "fde-k8s-sandbox-dev-505119")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# Ensure Google ADK / google-genai SDK sees Vertex AI configuration in os.environ
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", LOCATION)

# Vertex AI Search (Discovery Engine) Configuration
DISCOVERY_ENGINE_LOCATION = os.getenv("DISCOVERY_ENGINE_LOCATION", "global")
DATASTORE_ID = os.getenv("DISCOVERY_ENGINE_DATASTORE_ID", "k8s-custom-chunks-store")

# BigQuery & Firestore Telemetry Sinks
BQ_DATASET = os.getenv("BQ_TELEMETRY_DATASET", "k8s_copilot_telemetry")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_FEEDBACK_COLLECTION", "copilot_feedback")

# SPIFFE Workload Identity & Multi-Hop Agent Gateway Configuration
DEFAULT_TRUST_DOMAIN = os.getenv("SPIFFE_TRUST_DOMAIN", f"{PROJECT_ID}.svc.id.goog")
DEFAULT_SPIFFE_ID = os.getenv(
    "SPIFFE_ID",
    f"spiffe://{DEFAULT_TRUST_DOMAIN}/ns/default/sa/k8s-copilot-sa",
)
MCP_SPIFFE_ID = os.getenv(
    "MCP_SPIFFE_ID",
    f"spiffe://{DEFAULT_TRUST_DOMAIN}/ns/default/sa/mcp-k8s-docs-sa",
)
DEFAULT_SVID_TOKEN_PATH = os.getenv(
    "SPIFFE_SVID_TOKEN_PATH",
    "/var/run/secrets/spiffe.io/svid.jwt",
)

# Standalone MCP Microservice & Agent Gateway Enforcement
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "").rstrip("/")
ALLOWED_AGENT_SA_EMAIL = os.getenv(
    "ALLOWED_AGENT_SA_EMAIL",
    f"k8s-copilot-sa@{PROJECT_ID}.iam.gserviceaccount.com",
)
REQUIRE_END_USER_AUTH = os.getenv("REQUIRE_END_USER_AUTH", "false").lower() == "true"
REQUIRE_AGENT_AUTH = os.getenv("REQUIRE_AGENT_AUTH", "false").lower() == "true"

# CORS Allowed Origins (defaults to local Vite dev server)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if origin.strip()
]


