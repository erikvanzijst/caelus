variable "namespace" {
  description = "Namespace to deploy into"
  type = string
}

variable "domain" {
  description = "The base domain name of Caelus (e.g. app.deprutser.be)"
  type = string
}

variable "keycloak_admin_password" {
  description = "Keycloak admin password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}
