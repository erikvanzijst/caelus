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

# Keycloak client identity, keyed by Terraform workspace.
#
# These are maps rather than scalars because Terraform auto-loads
# `*.auto.tfvars` for EVERY workspace, so a single scalar cannot hold two
# per-environment values. Each environment now has its own Keycloak client
# (`freepod-prod` / `freepod-dev`, declared in tf/deps/keycloak-config), so a
# session minted for dev is not interchangeable with one minted for prod.
#
# The keys must be workspace names. **The dev workspace is named `default`, not
# `dev`** — see `local.is_prod_workspace`. A `dev` key would silently never
# match, so the validations below reject that mistake up front rather than
# failing later with an obscure index error.

variable "oauth2_proxy_client_ids" {
  description = "Keycloak client ID per Terraform workspace, e.g. { default = \"freepod-dev\", prod = \"freepod-prod\" }. Read from tf/deps outputs."
  type        = map(string)

  validation {
    condition     = alltrue([for k in ["default", "prod"] : contains(keys(var.oauth2_proxy_client_ids), k)])
    error_message = "oauth2_proxy_client_ids must have both a \"default\" (dev) and a \"prod\" key. The dev workspace is named `default`, not `dev`."
  }
}

variable "oauth2_proxy_client_secrets" {
  description = "Keycloak client secret per Terraform workspace. Read with `terraform output -raw freepod_{dev,prod}_client_secret` in tf/deps."
  type        = map(string)
  sensitive   = true

  validation {
    condition     = alltrue([for k in ["default", "prod"] : contains(keys(var.oauth2_proxy_client_secrets), k)])
    error_message = "oauth2_proxy_client_secrets must have both a \"default\" (dev) and a \"prod\" key. The dev workspace is named `default`, not `dev`."
  }
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
