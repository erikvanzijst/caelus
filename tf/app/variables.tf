variable "api_image" {
  description = "API container image incl. registry and tag (null = workspace default: :master prod, :latest dev)"
  type        = string
  default     = null
  nullable    = true
}

variable "ui_image" {
  description = "UI container image incl. registry and tag (null = workspace default: :master prod, :latest dev)"
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
