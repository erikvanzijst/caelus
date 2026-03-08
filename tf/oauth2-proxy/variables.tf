variable "namespace" {
  description = "Namespace to deploy into"
  type = string
}

variable "domain" {
  description = "The base domain name of Caelus (e.g. app.deprutser.be)"
  type = string
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
