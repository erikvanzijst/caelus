resource "kubernetes_namespace" "main" {
  metadata {
    name = local.namespace

    labels = {
      name        = local.namespace
      environment = local.environment
    }
  }
}
