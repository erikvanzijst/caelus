variable "namespace" {
  description = "Namespace to deploy into"
  type = string
}

variable "ns_login" {
  description = "The namespace oauth2-login is deployed into"
  type = string
}

variable "domain" {
  description = "The base domain name (e.g. app.deprutser.be)"
  type = string
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

variable "lb_ips" {
  description = "Load balancer IPs for hostname DNS validation"
  type        = list(string)
  default     = ["185.142.224.215"]
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
