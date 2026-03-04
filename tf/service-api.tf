resource "kubernetes_service" "api" {
  metadata {
    name      = "caelus-api"
    namespace = local.namespace
  }

  spec {
    selector = {
      app = "caelus-api"
    }

    port {
      name        = "http"
      port        = 8000
      target_port = "http"
    }

    type = "ClusterIP"
  }

  depends_on = [kubernetes_namespace.main]
}
