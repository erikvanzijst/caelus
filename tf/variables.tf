variable "api_image" {
  description = "API container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/erikvanzijst/caelus-api:latest"
}

variable "ui_image" {
  description = "UI container image (including registry and tag)"
  type        = string
  default     = "ghcr.io/erikvanzijst/caelus-ui:latest"
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

variable "keycloak_admin_password" {
  description = "Keycloak admin password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
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
  default     = "caelus@deprutser.be"
}

variable "db_password" {
  description = "Postgres password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}
