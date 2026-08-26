resource "kubernetes_deployment" "db_worker" {
  metadata {
    name      = "caelus-db-worker"
    namespace = var.namespace
    labels = {
      app = "caelus-db-worker"
    }
  }

  spec {
    # One sweeper: two would measure the same fleet twice and race each other
    # applying quota state.
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-db-worker"
      }
    }

    strategy {
      type = "Recreate"
    }

    template {
      metadata {
        labels = {
          app = "caelus-db-worker"
        }
        annotations = {
          "checksum/config" = sha256(jsonencode(kubernetes_config_map.api.data))
        }
      }

      spec {
        container {
          image             = var.api_image
          image_pull_policy = "Always"
          name              = "db-worker"
          command           = ["caelus", "db-worker"]

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

          # Deliberately no caelus-var-keys: every tick connects as
          # caelus_admin and none decrypts a tenant password, so the keyring
          # here would be exposure with no use.
          env_from {
            secret_ref {
              name = kubernetes_secret.tenant_db.metadata[0].name
            }
          }

          resources {
            requests = {
              memory = "128Mi"
              cpu    = "10m"
            }
            limits = {
              memory = "256Mi"
              cpu    = "200m"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      spec[0].template[0].metadata[0].annotations["kubectl.kubernetes.io/restartedAt"],
    ]
  }
}
