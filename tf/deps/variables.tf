variable "keycloak_admin_password" {
  description = "Keycloak admin password (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}
