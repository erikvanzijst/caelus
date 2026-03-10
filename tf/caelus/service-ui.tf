resource "kubernetes_service" "ui" {
  metadata {
    name      = "caelus-ui"
    namespace = var.namespace
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
}
