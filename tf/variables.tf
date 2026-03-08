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

variable "db_name" {
  description = "Postgres database name"
  type        = string
  default     = "caelus"
}

variable "db_user" {
  description = "Postgres username"
  type        = string
  default     = "caelus"
}

variable "db_password" {
  description = "Postgres password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}

variable "domain" {
  description = "External domain for ingress (null = workspace default)"
  type        = string
  default     = null
  nullable    = true
}

variable "api_replicas" {
  description = "Number of API pod replicas"
  type        = number
  default     = 1
}

variable "ui_replicas" {
  description = "Number of UI pod replicas"
  type        = number
  default     = 1
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
