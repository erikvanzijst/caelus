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
