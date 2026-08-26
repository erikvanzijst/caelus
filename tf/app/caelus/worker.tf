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
        annotations = {
          "checksum/config" = sha256(jsonencode(kubernetes_config_map.api.data))
          # Without this a bootstrap edit would sit in the ConfigMap unapplied
          # until some unrelated restart happened to pick it up.
          "checksum/tenant-bootstrap" = sha256(kubernetes_config_map.tenant_db_bootstrap.data["tenant-bootstrap.sql"])
        }
      }

      spec {
        service_account_name = kubernetes_service_account.api.metadata[0].name

        init_container {
          name              = "migrate"
          image             = var.api_image
          image_pull_policy = "Always"
          command           = ["alembic", "upgrade", "head"]

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

        # Bootstraps the tenant PostgreSQL cluster: the PUBLIC revocations,
        # caelus_admin and its grants, and pgbouncer_auth with its lookup
        # function. Init containers run in order, so this follows `migrate`.
        #
        # It gates the worker deliberately (design D6): a failed bootstrap
        # fails the init container, the pod never becomes ready, and the
        # previous ReplicaSet keeps reconciling. The alternative -- a Terraform
        # Job -- would let a worker start and then fail every reconcile that
        # touches a database.
        #
        # The worker rather than the API because it is the first process to
        # write to the tenant cluster, and because gating the API on it would
        # couple control-plane startup to tenant-cluster availability.
        init_container {
          name    = "tenant-db-bootstrap"
          image   = local.tenant_db_image
          command = ["/bin/sh", "-c"]
          args = [
            <<-EOT
              exec psql -v ON_ERROR_STOP=1 \
                -v caelus_admin_password="$CAELUS_ADMIN_PASSWORD" \
                -v pgbouncer_auth_password="$PGBOUNCER_AUTH_PASSWORD" \
                -f /bootstrap/tenant-bootstrap.sql
            EOT
          ]

          env {
            name  = "PGHOST"
            value = "caelus-tenant-postgres.${var.namespace}.svc.cluster.local"
          }

          env {
            name  = "PGPORT"
            value = "5432"
          }

          # The one place a superuser credential is used. Every long-running
          # process below connects as caelus_admin instead.
          env {
            name  = "PGUSER"
            value = "postgres"
          }

          env {
            name  = "PGDATABASE"
            value = "postgres"
          }

          env {
            name = "PGPASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.tenant_db_bootstrap.metadata[0].name
                key  = "POSTGRES_PASSWORD"
              }
            }
          }

          env {
            name = "CAELUS_ADMIN_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.tenant_db_bootstrap.metadata[0].name
                key  = "CAELUS_ADMIN_PASSWORD"
              }
            }
          }

          env {
            name = "PGBOUNCER_AUTH_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.tenant_db_bootstrap.metadata[0].name
                key  = "PGBOUNCER_AUTH_PASSWORD"
              }
            }
          }

          volume_mount {
            name       = "tenant-db-bootstrap"
            mount_path = "/bootstrap"
            read_only  = true
          }
        }

        container {
          image             = var.api_image
          image_pull_policy = "Always"
          name              = "worker"
          command           = ["caelus", "worker", "--concurrency", "4"]

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

          env_from {
            secret_ref {
              name = kubernetes_secret.s3.metadata[0].name
            }
          }

          # The same keyring the API holds, and it must be the same: the worker
          # decrypts the release snapshot the API encrypted. A worker missing a
          # key the API is already writing with fails every rollout -- which is
          # what makes introducing a key two-phase (see variables.tf).
          env_from {
            secret_ref {
              name = kubernetes_secret.var_keys.metadata[0].name
            }
          }

          # The tenant cluster's admin credential and addresses. The reconciler
          # provisions a database per deployment whose product opts in, so the
          # worker holds this for the same reason it holds the Garage admin
          # token next door.
          env_from {
            secret_ref {
              name = kubernetes_secret.tenant_db.metadata[0].name
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

        volume {
          name = "tenant-db-bootstrap"
          config_map {
            name = kubernetes_config_map.tenant_db_bootstrap.metadata[0].name
          }
        }
      }
    }
  }

  # Ignore restartedAt annotations written by `kubectl rollout restart`
  lifecycle {
    ignore_changes = [
      spec[0].template[0].metadata[0].annotations["kubectl.kubernetes.io/restartedAt"],
    ]
  }

  depends_on = [kubernetes_cluster_role_binding.api]
}
