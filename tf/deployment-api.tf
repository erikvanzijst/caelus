resource "kubernetes_deployment" "api" {
  metadata {
    name      = "caelus-api"
    namespace = local.namespace
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
        service_account_name = kubernetes_service_account.api.metadata[0].name

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

          volume_mount {
            name       = "sqlite-data"
            mount_path = "/app/db"
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
        volume {
          name = "sqlite-data"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.sqlite_pvc.metadata[0].name
          }
        }
      }
    }
  }

  depends_on = [kubernetes_namespace.main, kubernetes_cluster_role_binding.api]
}
