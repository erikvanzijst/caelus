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
