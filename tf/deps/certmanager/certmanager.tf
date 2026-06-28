# cert-manager on the freepod cluster. Mirrors the homelab helm/cert-manager
# module. Installs CRDs and runs in its own `cert-manager` namespace.
resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true

  repository = "https://charts.jetstack.io"
  chart      = "cert-manager"
  version    = var.chart_version

  set {
    name  = "installCRDs"
    value = "true"
  }
}
