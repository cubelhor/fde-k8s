output "backend_url" {
  description = "The deployed Cloud Run service URL"
  value       = google_cloud_run_v2_service.backend.uri
}

output "service_account_email" {
  description = "The service account email used by the Cloud Run backend"
  value       = google_service_account.copilot_backend.email
}
