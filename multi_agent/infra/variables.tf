variable "project_id" {
  description = "The Google Cloud Project ID"
  type        = string
  default     = "fde-k8s-sandbox-dev-505119"
}

variable "project_number" {
  description = "The Google Cloud Project Number (used for VPC Service Controls perimeter)"
  type        = string
  default     = ""
}

variable "access_policy_id" {
  description = "Organization Access Context Manager Policy ID for VPC Service Controls (VPC-SC)"
  type        = string
  default     = ""
}

variable "region" {
  description = "The Google Cloud region for deployment"
  type        = string
  default     = "us-central1"
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
