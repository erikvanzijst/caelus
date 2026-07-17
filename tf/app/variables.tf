variable "api_image" {
  description = "API container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/erikvanzijst/caelus/api:latest"
}

variable "ui_image" {
  description = "UI container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/erikvanzijst/caelus/ui:latest"
}

variable "namespace" {
  description = "Kubernetes namespace for all resources (null = workspace default)"
  type        = string
  default     = null
  nullable    = true
}


variable "domain" {
  description = "External domain for ingress (null = workspace default)"
  type        = string
  default     = null
  nullable    = true
}

variable "environment" {
  description = "Namespace label for environment (null = workspace default)"
  type        = string
  default     = null
  nullable    = true
}

variable "oauth2_proxy_client_secret" {
  description = "OAuth2-proxy client secret for Keycloak"
  type        = string
  sensitive   = true
}

variable "oauth2_proxy_cookie_secret" {
  description = "Cookie secret for oauth2-proxy (32 bytes, base64 encoded)"
  type        = string
  sensitive   = true
}

variable "smtp_password" {
  description = "SMTP password for outbound email (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}

variable "smtp_username" {
  description = "SMTP username for outbound email"
  type        = string
  default     = "noreply@freepod.eu"
}

variable "db_password" {
  description = "Postgres password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}

variable "mollie_api_key" {
  description = "Mollie API Key"
  type        = string
  sensitive   = true
}

variable "sshpiper_port" {
  description = "Cluster-side SSH port for the SFTP entry point (null = workspace default: 2222 prod, 2223 dev)"
  type        = number
  default     = null
  nullable    = true
}

variable "google_client_id" {
  description = "Google OAuth Client ID for Google Drive API integration"
  type = string
}

variable "google_client_secret" {
  description = "Google OAuth Client Secret for Google Drive API integration"
  type = string
  sensitive = true
}

variable "google_app_id" {
  description = "The Freepod project/app number in the Google Developer Console linking the Picker API Key and Drive OAuth client"
  type = string
}

variable "google_api_key" {
  description = "Google Picker API identifier"
  type = string
}
