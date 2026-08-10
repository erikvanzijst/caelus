variable "realm_name" {
  description = "Name of the Freepod end-user realm. End users live here, never in `master` (Keycloak's administrative realm)."
  type        = string
  default     = "freepod"
}

variable "prod_domain" {
  description = "Public hostname of the production Freepod environment, served by the freepod-prod client."
  type        = string
  default     = "freepod.eu"
}

variable "dev_domain" {
  description = "Public hostname of the development Freepod environment, served by the freepod-dev client."
  type        = string
  default     = "dev.freepod.eu"
}

variable "grafana_domain" {
  description = "Public hostname for Grafana, served by the grafana client. Keep in sync with prometheus/variables.tf."
  type        = string
  default     = "grafana.freepod.eu"
}

# --- SMTP ---
#
# A realm without working SMTP fails email verification and self-service
# password reset *silently*, and password reset is how every account seeded
# without a credential obtains one. That makes this block the single point of
# failure for all access during the cutover.
#
# Mail goes through the in-cluster relay (../mailer), which holds the real
# upstream credentials — the same arrangement Alertmanager uses (see
# ../prometheus/prometheus.tf, smtp_smarthost). Do NOT wire the root module's
# smtp_* variables in here: those are the *relay's own upstream* purelymail
# credentials, not Keycloak's, and pointing the realm straight at purelymail
# with them would exercise a mail path that has never been tested.

variable "smtp_host" {
  description = "SMTP endpoint for realm email. Defaults to the in-cluster mailer relay, which holds the upstream credentials."
  type        = string
  default     = "smtp.mailer.svc.cluster.local"
}

variable "smtp_port" {
  description = "Port for the SMTP endpoint. The relay listens on plain 25 inside the cluster."
  type        = string
  default     = "25"
}

variable "smtp_from" {
  description = "Envelope/header From address for realm email."
  type        = string
  default     = "noreply@freepod.eu"
}

variable "smtp_from_display_name" {
  description = "Display name shown alongside the From address."
  type        = string
  default     = "Freepod"
}

variable "smtp_reply_to" {
  description = "Reply-To address for realm email."
  type        = string
  default     = "noreply@freepod.eu"
}
