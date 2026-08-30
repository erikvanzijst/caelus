output "namespace" {
  description = "Kubernetes namespace"
  value       = var.namespace
}

output "api_service_name" {
  description = "API Kubernetes service name"
  value       = kubernetes_service.api.metadata[0].name
}

output "ui_service_name" {
  description = "UI Kubernetes service name"
  value       = kubernetes_service.ui.metadata[0].name
}

output "ingress_host" {
  description = "External hostname"
  value       = var.domain
}

output "api_endpoint" {
  description = "Full API endpoint URL"
  value       = "https://${var.domain}/api"
}

# Consumed by tf/app/sshpiper, which assembles the resolver's DATABASE_URL from
# it. The role is created here because it lives in the platform database; the
# process that uses it runs in the SSH edge's namespace, which cannot read a
# Secret from this one.
output "ssh_resolver_db_password" {
  description = "Password for the caelus_ssh_resolver read-only role"
  value       = random_password.ssh_resolver_db.result
  sensitive   = true
}

output "ssh_resolver_db_role" {
  description = "Role name the SSH auth resolver connects as"
  value       = "caelus_ssh_resolver"
}
