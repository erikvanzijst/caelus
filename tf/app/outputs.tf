output "namespace" {
  description = "Kubernetes namespace"
  value       = kubernetes_namespace.caelus.metadata[0].name
}

output "api_service_name" {
  description = "API Kubernetes service name"
  value       = module.caelus.api_service_name
}

output "ui_service_name" {
  description = "UI Kubernetes service name"
  value       = module.caelus.ui_service_name
}

output "ingress_host" {
  description = "External hostname"
  value       = local.domain
}

output "api_endpoint" {
  description = "Full API endpoint URL"
  value       = "https://${local.domain}/api"
}

# The public half of this environment's upstream key. The `caelus-sftp` chart
# carries it as the sole key each sidecar trusts, and the chart is not something
# Terraform owns -- so read it from here rather than from a copy:
#
#   terraform output -raw sshpiper_upstream_public_key
output "sshpiper_upstream_public_key" {
  description = "Public half of the SSH edge's upstream key, for the caelus-sftp chart"
  value       = module.sshpiper.upstream_public_key
}
