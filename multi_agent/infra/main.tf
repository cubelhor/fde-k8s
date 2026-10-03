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

# --- Google Cloud Storage Bucket for Kubernetes Hugo Markdown Documentation Corpus ---
resource "google_storage_bucket" "k8s_docs_corpus" {
  project                     = var.project_id
  name                        = "k8s-docs-${var.project_id}"
  location                    = "EU"
  uniform_bucket_level_access = true
  force_destroy               = false
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

# --- Firestore IAM Role for User Feedback (copilot_feedback) ---
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.copilot_backend.email}"
}

# --- BigQuery Telemetry Dataset & Cloud Logging Sink (TOKEN_METRICS & USER_FEEDBACK) ---
resource "google_bigquery_dataset" "telemetry" {
  project       = var.project_id
  dataset_id    = "k8s_copilot_telemetry"
  friendly_name = "Kubernetes Troubleshooting Copilot Telemetry"
  description   = "Stores structured TOKEN_METRICS, USER_FEEDBACK, and latency telemetry routed from Cloud Logging."
  location      = var.region
}

resource "google_logging_project_sink" "bigquery_token_metrics" {
  project                = var.project_id
  name                   = "k8s-copilot-token-metrics-bq-sink"
  destination            = "bigquery.googleapis.com/projects/${var.project_id}/datasets/${google_bigquery_dataset.telemetry.dataset_id}"
  filter                 = "jsonPayload.event_type=\"TOKEN_METRICS\" OR jsonPayload.event_type=\"USER_FEEDBACK\""
  unique_writer_identity = true

  bigquery_options {
    use_partitioned_tables = true
  }
}

resource "google_bigquery_dataset_iam_member" "log_sink_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.telemetry.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = google_logging_project_sink.bigquery_token_metrics.writer_identity
}

# --- Looker BI Dashboard View: Cluster Anomaly Frequency, Latency Trends & Simulated MTTR ---
resource "google_bigquery_table" "looker_bi_dashboard_view" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.telemetry.dataset_id
  table_id            = "v_looker_incident_bi_metrics"
  deletion_protection = false

  view {
    use_legacy_sql = false
    query          = <<-SQL
      WITH token_events AS (
        SELECT
          jsonPayload.incident_id AS incident_id,
          TIMESTAMP(timestamp) AS diagnosed_at,
          COALESCE(jsonPayload.error_type, 'GeneralClusterAnomaly') AS error_type,
          COALESCE(jsonPayload.cluster_context, 'unknown') AS cluster_context,
          COALESCE(jsonPayload.model_name, 'gemini-2.5-pro') AS model_name,
          COALESCE(jsonPayload.execution_mode, 'async') AS execution_mode,
          CAST(jsonPayload.prompt_tokens AS INT64) AS prompt_tokens,
          CAST(jsonPayload.cached_tokens AS INT64) AS cached_tokens,
          CAST(jsonPayload.completion_tokens AS INT64) AS completion_tokens,
          CAST(jsonPayload.total_tokens AS INT64) AS total_tokens,
          CAST(jsonPayload.estimated_cost_usd AS FLOAT64) AS estimated_cost_usd,
          CAST(jsonPayload.latency_ms AS FLOAT64) AS total_latency_ms,
          CAST(jsonPayload.planner_latency_ms AS FLOAT64) AS planner_latency_ms,
          CAST(jsonPayload.executor_latency_ms AS FLOAT64) AS executor_latency_ms
        FROM `${var.project_id}.${google_bigquery_dataset.telemetry.dataset_id}.run_googleapis_com_stdout`
        WHERE jsonPayload.event_type = 'TOKEN_METRICS'
      ),
      feedback_events AS (
        SELECT
          jsonPayload.incident_id AS incident_id,
          ARRAY_AGG(jsonPayload.rating IGNORE NULLS ORDER BY timestamp DESC LIMIT 1)[OFFSET(0)] AS final_rating,
          MAX(CAST(jsonPayload.session_duration_sec AS FLOAT64)) AS session_duration_sec,
          MAX(CAST(jsonPayload.baseline_mttr_minutes AS FLOAT64)) AS baseline_mttr_minutes,
          MAX(CAST(jsonPayload.simulated_resolution_minutes AS FLOAT64)) AS simulated_resolution_minutes,
          MAX(CAST(jsonPayload.simulated_mttr_saved_minutes AS FLOAT64)) AS simulated_mttr_saved_minutes,
          COUNTIF(jsonPayload.copied_command_entry.command IS NOT NULL) AS commands_copied_count
        FROM `${var.project_id}.${google_bigquery_dataset.telemetry.dataset_id}.run_googleapis_com_stdout`
        WHERE jsonPayload.event_type = 'USER_FEEDBACK'
        GROUP BY jsonPayload.incident_id
      )
      SELECT
        t.error_type,
        t.execution_mode,
        COUNT(DISTINCT t.incident_id) AS incident_count,
        ROUND(
          COUNT(DISTINCT t.incident_id) * 100.0 / SUM(COUNT(DISTINCT t.incident_id)) OVER (),
          2
        ) AS anomaly_share_pct,
        ROUND(AVG(t.total_latency_ms), 2) AS avg_total_latency_ms,
        ROUND(AVG(t.planner_latency_ms), 2) AS avg_planner_latency_ms,
        ROUND(AVG(t.executor_latency_ms), 2) AS avg_executor_latency_ms,
        ROUND(AVG(t.estimated_cost_usd), 6) AS avg_cost_per_query_usd,
        ROUND(AVG(t.total_tokens), 1) AS avg_total_tokens,
        COUNTIF(f.final_rating = 'up') AS thumbs_up_count,
        COUNTIF(f.final_rating = 'down') AS thumbs_down_count,
        SUM(COALESCE(f.commands_copied_count, 0)) AS total_commands_copied,
        ROUND(AVG(COALESCE(f.session_duration_sec, 180.0)), 2) AS avg_sre_session_duration_sec,
        ROUND(AVG(COALESCE(f.baseline_mttr_minutes, 30.0)), 2) AS avg_baseline_mttr_minutes,
        ROUND(AVG(COALESCE(f.simulated_resolution_minutes, 3.0)), 2) AS avg_simulated_resolution_minutes,
        ROUND(AVG(COALESCE(f.simulated_mttr_saved_minutes, 27.0)), 2) AS avg_mttr_saved_minutes
      FROM token_events t
      LEFT JOIN feedback_events f
        ON t.incident_id = f.incident_id
      GROUP BY
        t.error_type,
        t.execution_mode
      ORDER BY
        incident_count DESC
    SQL
  }
}


