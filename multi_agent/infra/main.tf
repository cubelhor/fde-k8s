terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# --- Service Account for Copilot Backend ---
resource "google_service_account" "copilot_backend" {
  account_id   = "k8s-copilot-backend-sa"
  display_name = "K8s Troubleshooting Copilot Backend Service Account"
}

# --- IAM Roles for Vertex AI, Discovery Engine, and Telemetry ---
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

resource "google_project_iam_member" "discovery_engine_viewer" {
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

# --- Google Cloud Secret Manager for External Service & Telemetry Collector Keys ---
resource "google_secret_manager_secret" "telemetry_collector_api_key" {
  project   = var.project_id
  secret_id = "telemetry-collector-api-key"

  replication {
    auto {}
  }
}

resource "google_project_iam_member" "secret_manager_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

resource "google_project_iam_member" "gcs_chunks_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

# --- Cloud Run Backend Service ---
resource "google_cloud_run_v2_service" "backend" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.copilot_backend.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/k8s-copilot/${var.service_name}:${var.image_tag}"

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "K8S_DOCS_GCS_BUCKET"
        value = "k8s-docs-${var.project_id}"
      }
      env {
        name  = "MCP_RETRIEVAL_MODE"
        value = "vertex"
      }
      env {
        name  = "SPIFFE_TRUST_DOMAIN"
        value = "${var.project_id}.svc.id.goog"
      }
      env {
        name  = "SPIFFE_ID"
        value = "spiffe://${var.project_id}.svc.id.goog/ns/default/sa/${google_service_account.copilot_backend.account_id}"
      }
    }
  }
}

# --- Allow Unauthenticated Invocations for Demo Frontend ---
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = google_cloud_run_v2_service.backend.project
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
