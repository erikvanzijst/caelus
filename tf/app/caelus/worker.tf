resource "kubernetes_deployment" "worker" {
  metadata {
    name      = "caelus-worker"
    namespace = var.namespace
    labels = {
      app = "caelus-worker"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-worker"
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
          app = "caelus-worker"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.api.metadata[0].name

        init_container {
          name    = "migrate"
          image   = var.api_image
          command = ["alembic", "upgrade", "head"]

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
        }

        container {
          image   = var.api_image
          name    = "worker"
          command = ["caelus", "worker", "--follow"]

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

  depends_on = [kubernetes_cluster_role_binding.api]
}
