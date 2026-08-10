variable "namespace" {
  description = "Namespace to deploy into"
  type        = string
}

variable "domain" {
  description = "The base domain name of Caelus (e.g. freepod.eu)"
  type        = string
}

# Scalars, not maps: the root module selects the value for the current
# workspace and passes it down. This module deploys one oauth2-proxy for one
# environment and has no business knowing about the others.

variable "oauth2_proxy_client_id" {
  description = "Keycloak client ID this oauth2-proxy authenticates as (freepod-prod or freepod-dev)."
  type        = string
}

variable "oauth2_proxy_client_secret" {
  description = "OAuth2-proxy client secret for oauth2-proxy"
  type        = string
  sensitive   = true
}

variable "keycloak_realm" {
  description = "Keycloak realm that issues tokens for Freepod end users. Not `master`, which is Keycloak's administrative realm."
  type        = string
  default     = "freepod"
}

variable "keycloak_url" {
  description = "Base URL of the Keycloak instance. Combined with keycloak_realm to build the issuer and backend-logout URLs."
  type        = string
  default     = "https://keycloak.freepod.eu"
}

variable "allowed_groups" {
  description = <<-EOT
    Keycloak groups permitted to authenticate through this proxy. Empty means
    no group restriction (production). Set to ["freepod-dev"] for non-prod, so
    dev is closed by authorization rather than by registration — registration
    is realm-level and the realm is shared, so nobody needs a second account.

    Bare group names, NOT paths: the realm's group membership mapper has
    full_path = false, so the claim carries `freepod-dev`, not `/freepod-dev`.

    Enforced on every request — oauth2-proxy applies the check on the AuthOnly
    endpoint that Traefik's forwardAuth hits and clears the session cookie on
    denial, so removing someone from the group takes effect on their next
    request rather than at token expiry.

    Caveat: skip_auth_routes bypass this entirely, because oauth2-proxy returns
    early before the authorization check. Dev's anonymous catalog reads stay
    public by design.
  EOT
  type        = list(string)
  default     = []
}

variable "oauth2_proxy_cookie_secret" {
  description = "Cookie secret for oauth2-proxy (32 bytes, base64 encoded)"
  type        = string
  sensitive   = true
}
