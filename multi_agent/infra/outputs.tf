output "backend_url" {
  description = "The deployed Cloud Run Agentic Backend service URL"
  value       = google_cloud_run_v2_service.backend.uri
}

output "mcp_server_url" {
  description = "The deployed standalone MCP Server Cloud Run service URL"
  value       = google_cloud_run_v2_service.mcp_server.uri
}

output "frontend_bucket_url" {
  description = "The static GCS hosting bucket URL for the React frontend"
  value       = google_storage_bucket.frontend_static_site.url
}

output "service_account_email" {
  description = "The service account email used by the Cloud Run Agentic Backend"
  value       = google_service_account.copilot_backend.email
}

output "mcp_service_account_email" {
  description = "The service account email used by the standalone MCP Server"
  value       = google_service_account.mcp_server.email
}

