resource "kubernetes_deployment" "ui" {
  metadata {
    name      = "caelus-ui"
    namespace = var.namespace
    labels = {
      app = "caelus-ui"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-ui"
      }
    }

    strategy {
      type = "RollingUpdate"
      rolling_update {
        max_surge       = 1
        max_unavailable = 0
      }
    }

    template {
      metadata {
        labels = {
          app = "caelus-ui"
        }
      }

      spec {
        container {
          image = var.ui_image
          name  = "ui"

          port {
            name           = "http"
            container_port = 80
            protocol       = "TCP"
          }

          # resources {
          #   requests = {
          #     memory = "64Mi"
          #     cpu    = "100m"
          #   }
          #   limits = {
          #     memory = "128Mi"
          #     cpu    = "200m"
          #   }
          # }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main]
}
