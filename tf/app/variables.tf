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

variable "builder_image" {
  description = "Image that runs tenant builds, published by hand from products/custom/builder/ on its own cadence"
  type        = string
  default     = "registry.home/caelus/builder:0.1.2"
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

# Garage S3 object store, keyed by Terraform workspace.
#
# Maps for the same reason as oauth2_proxy_client_ids above: `*.auto.tfvars` is
# auto-loaded for EVERY workspace, so a scalar cannot hold two per-environment
# values. One Garage instance serves both environments (tf/deps is
# workspace-less) and they are separated by bucket and access key, so getting
# this wrong does not fail loudly — it silently points dev at prod's objects.
# Hence the validations, and the same reminder: **the dev workspace is named
# `default`, not `dev`**.
#
# Read the values from tf/deps:
#   terraform output -raw garage_access_key_id_dev
#   terraform output -raw garage_secret_access_key_dev   (and the prod pair)

variable "s3_buckets" {
  description = "Garage bucket per Terraform workspace, e.g. { default = \"dev\", prod = \"prod\" }."
  type        = map(string)
  default = {
    default = "dev"
    prod    = "prod"
  }

  validation {
    condition     = alltrue([for k in ["default", "prod"] : contains(keys(var.s3_buckets), k)])
    error_message = "s3_buckets must have both a \"default\" (dev) and a \"prod\" key. The dev workspace is named `default`, not `dev`."
  }
}

variable "s3_access_key_ids" {
  description = "Garage S3 access key ID per Terraform workspace. Read from tf/deps outputs."
  type        = map(string)

  validation {
    condition     = alltrue([for k in ["default", "prod"] : contains(keys(var.s3_access_key_ids), k)])
    error_message = "s3_access_key_ids must have both a \"default\" (dev) and a \"prod\" key. The dev workspace is named `default`, not `dev`."
  }
}

variable "s3_secret_access_keys" {
  description = "Garage S3 secret access key per Terraform workspace. Read with `terraform output -raw garage_secret_access_key_{dev,prod}` in tf/deps."
  type        = map(string)
  sensitive   = true

  validation {
    condition     = alltrue([for k in ["default", "prod"] : contains(keys(var.s3_secret_access_keys), k)])
    error_message = "s3_secret_access_keys must have both a \"default\" (dev) and a \"prod\" key. The dev workspace is named `default`, not `dev`."
  }
}

# Scalars, not maps: one Garage serves both environments at one hostname.
variable "s3_endpoint_url" {
  description = "Garage S3 endpoint. Path-style addressing is mandatory — see api/app/config.py."
  type        = string
  default     = "https://blob.freepod.eu"
}

variable "s3_region" {
  description = "SigV4 signing region. Garage's default; must match tf/deps."
  type        = string
  default     = "garage"
}

# --- Per-deployment object storage ------------------------------------------
# The API provisions a bucket and access key per storage-enabled deployment, so
# it needs a Garage admin credential of its own. Not per-workspace, unlike the S3
# credentials above: every environment provisions on the one shared instance and
# the scope is identical, so both workspaces take the same value.
#
# `terraform output -raw garage_caelus_api_admin_token` in tf/deps.

variable "garage_admin_url" {
  description = "In-cluster Garage admin API URL. Never routed by an Ingress; see tf/deps/garage/ingress.tf."
  type        = string
  default     = "http://garage.garage.svc.cluster.local:3903"
}

variable "garage_admin_token" {
  description = "Scoped, non-expiring Garage admin token for per-deployment bucket provisioning. From tf/deps."
  type        = string
  sensitive   = true
}

variable "loki_base_url" {
  description = "In-cluster Loki query API URL. Never Ingress-routed; only the API may reach it."
  type        = string
  default     = "http://loki.monitoring.svc.cluster.local:3100"
}

variable "log_keepalive_seconds" {
  description = "Interval between SSE keepalives on an open log stream. Must stay below the shortest connection timeout in the client -> homelab HAProxy -> Traefik -> API path. HAProxy's timeouts are operator-configured and not in this repo, so this is a variable rather than a constant -- measure against the live edge before changing it."
  type        = number
  default     = 15
}
