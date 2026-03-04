resource "kubernetes_service" "ui" {
  metadata {
    name      = "caelus-ui"
    namespace = local.namespace
  }

  spec {
    selector = {
      app = "caelus-ui"
    }

    port {
      name        = "http"
      port        = 80
      target_port = "http"
    }

    type = "ClusterIP"
  }

  depends_on = [kubernetes_namespace.main]
}
