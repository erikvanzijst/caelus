resource "kubernetes_deployment" "api" {
  metadata {
    name      = "caelus-api"
    namespace = var.namespace
    labels = {
      app = "caelus-api"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-api"
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
          app = "caelus-api"
        }
      }

      spec {
        container {
          image = var.api_image
          name  = "api"

          port {
            name           = "http"
            container_port = 8000
            protocol       = "TCP"
          }

          env_from {
            config_map_ref {
              name = "caelus-api-config"
            }
          }

          env_from {
            secret_ref {
              name = "caelus-db"
            }
          }

          # resources {
          #   requests = {
          #     memory = "128Mi"
          #     cpu    = "100m"
          #   }
          #   limits = {
          #     memory = "256Mi"
          #     cpu    = "200m"
          #   }
          # }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main]
}
