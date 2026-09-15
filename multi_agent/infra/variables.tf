variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "fde-k8s-sandbox-dev-505119"
}

variable "region" {
  description = "The Google Cloud region for deployment"
  type        = string
  default     = "europe-west4"
}

variable "service_name" {
  description = "Name of the Cloud Run backend service"
  type        = string
  default     = "k8s-troubleshooting-copilot"
}

variable "image_tag" {
  description = "Container image tag for Cloud Run"
  type        = string
  default     = "latest"
}
