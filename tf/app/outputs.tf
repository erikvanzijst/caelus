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
