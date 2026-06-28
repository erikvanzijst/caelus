variable "keycloak_admin_password" {
  description = "Keycloak admin password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}
variable "smtp_host" {
  description = "SMTP server (e.g. smtp.example.com)"
  type        = string
}

variable "smtp_port" {
  description = "SMTP server port (e.g. 587)"
  type        = string
}

variable "smtp_username" {
  description = "SMTP username"
  type        = string
}

variable "smtp_password" {
  description = "SMTP password"
  type        = string
  sensitive   = true
}

# --- TLS / cert-manager (app-tls-termination) ---

variable "cloudflare_api_token" {
  description = "Cloudflare API token with edit rights on the freepod.eu DNS zone (DNS-01 wildcard issuance). Use secrets.auto.tfvars."
  type        = string
  sensitive   = true
}

variable "cloudflare_email" {
  description = "Cloudflare account email. Declared for parity with the homelab tfvars; the DNS-01 token solver does not use it."
  type        = string
  default     = ""
}

variable "letsencrypt_email" {
  description = "ACME account email for the Let's Encrypt ClusterIssuers."
  type        = string
}

variable "haproxy_edge_ip" {
  description = "IP of the homelab HAProxy edge, trusted for PROXY protocol on freepod Traefik entrypoints. The source IP freepod sees for passthrough traffic (the homelab node). Override in secrets.auto.tfvars if it differs."
  type        = string
  default     = "192.168.0.12/32"
}
