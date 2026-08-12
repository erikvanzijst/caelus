variable "namespace" {
  description = "Namespace to deploy into"
  type        = string
}

variable "ns_login" {
  description = "The namespace oauth2-login is deployed into"
  type        = string
}

variable "domain" {
  description = "The base domain name (e.g. freepod.eu)"
  type        = string
}

variable "api_image" {
  description = "API container image (including registry and tag)"
  type        = string
}

variable "ui_image" {
  description = "UI container image (including registry and tag)"
  type        = string
}

variable "rbac_name" {
  description = "Cluster-scoped RBAC object names must be unique per deployment."
  type        = string
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
  description = "Postgres password"
  type        = string
  sensitive   = true
}

variable "wildcard_domains" {
  description = "Freely available wildcard domains"
  type        = list(string)
}

variable "mollie_api_key" {
  description = "Mollie API Key"
  type        = string
  sensitive   = true
}

# NOTE: These are currently configured in api/.env
# variable "reserved_hostnames" {
#   description = "Hostnames that cannot be claimed by users"
#   type        = list(string)
# }

variable "sshpiper_namespace" {
  description = "Namespace of this environment's sshpiper SFTP router (for the tenant NetworkPolicy carve-out)"
  type        = string
}

variable "sftp_host" {
  description = "User-facing SFTP host advertised by the API/UI (e.g. freepod.eu / dev.freepod.eu)"
  type        = string
}

variable "sftp_port" {
  description = "User-facing SFTP port advertised by the API/UI (22 prod, 23 dev)"
  type        = number
}

# --- Garage S3 object store (this environment's slice) ---------------------

variable "s3_endpoint_url" {
  description = "Garage S3 endpoint URL"
  type        = string
}

variable "s3_region" {
  description = "SigV4 signing region for the Garage S3 API"
  type        = string
}

variable "s3_bucket" {
  description = "This environment's Garage bucket"
  type        = string
}

variable "s3_access_key_id" {
  description = "Access key ID scoped to this environment's bucket only"
  type        = string
}

variable "s3_secret_access_key" {
  description = "Secret access key for s3_access_key_id"
  type        = string
  sensitive   = true
}
