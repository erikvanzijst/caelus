variable "namespace" {
  description = "Namespace to deploy into"
  type        = string
}

variable "grafana_domain" {
  description = "Public hostname for Grafana (the only externally exposed monitoring UI)."
  type        = string
  default     = "grafana.freepod.eu"
}

variable "grafana_admin_password" {
  description = "Grafana local admin password (break-glass; primary auth is Keycloak OIDC)."
  type        = string
  sensitive   = true
}

variable "alert_email_to" {
  description = "Recipient address for Alertmanager alert emails."
  type        = string
}

variable "grafana_oidc_client_id" {
  description = "Keycloak OIDC client ID for Grafana."
  type        = string
}

variable "grafana_oidc_client_secret" {
  description = "Keycloak OIDC client secret for Grafana."
  type        = string
  sensitive   = true
}
