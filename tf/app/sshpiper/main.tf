# Per-environment sshpiperd: the single SSH entry point for tenant SSH
# access. Routes connections by username to per-deployment sidecars, asking
# the SSH auth resolver (ssh-auth/) which one and whether
# the offered key may open it.
resource "tls_private_key" "host_key" {
  algorithm = "ED25519"
}

resource "kubernetes_secret" "server_key" {
  metadata {
    name      = "sshpiper-server-key"
    namespace = var.namespace
  }

  data = {
    server_key = tls_private_key.host_key.private_key_openssh
  }
}

# Derived, never stored: the public half of the upstream key, which the
# `caelus-sftp` chart carries so each sidecar trusts it. Exposed as an output so
# the chart is filled from the same value the cluster runs on, rather than from
# a copy someone kept.
data "tls_public_key" "upstream" {
  private_key_openssh = var.upstream_private_key
}

# The credential the edge presents to every SFTP sidecar in this environment.
# It is mounted into the resolver alone -- sshpiperd never reads it, it is
# handed the key inline on each connection -- and no tenant namespace holds it.
# Tenants hold only the public half their sidecar trusts, which grants nothing.
resource "kubernetes_secret" "upstream_key" {
  metadata {
    name      = "sshpiper-upstream-key"
    namespace = var.namespace
  }

  data = {
    ssh_upstream_key = var.upstream_private_key
  }
}

# The resolver's database credential: the read-only caelus_ssh_resolver role,
# which can SELECT two tables and do nothing else.
resource "kubernetes_secret" "resolver_db" {
  metadata {
    name      = "ssh-resolver-db"
    namespace = var.namespace
  }

  data = {
    CAELUS_SSH_RESOLVER_DATABASE_URL = var.resolver_database_url
  }
}

resource "kubernetes_service_account" "sshpiper" {
  metadata {
    name      = "sshpiper"
    namespace = var.namespace
  }
}

# sshpiperd daemon configuration (all non-secret; the host key is a mounted
# Secret, not here). See https://github.com/tg123/sshpiper for the flags.
resource "kubernetes_config_map" "sshpiper" {
  metadata {
    name      = "sshpiper-config"
    namespace = var.namespace
  }

  data = {
    SSHPIPERD_GRPC_ENDPOINT         = "127.0.0.1:${var.resolver_port}"
    SSHPIPERD_GRPC_INSECURE         = "true"
    SSHPIPERD_SERVER_KEY            = "/serverkey/ssh_host_ed25519_key"
    SSHPIPERD_LOG_LEVEL             = "info"
    SSHPIPERD_DROP_HOSTKEYS_MESSAGE = "true"
  }
}

resource "kubernetes_deployment" "sshpiper" {
  metadata {
    name      = "sshpiper"
    namespace = var.namespace
    labels = {
      app = "sshpiper"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "sshpiper"
      }
    }

    template {
      metadata {
        labels = {
          app = "sshpiper"
        }
        # Roll the pod when the config changes; env_from does not restart pods
        # on its own, so without this a config edit would silently run stale.
        annotations = {
          "checksum/config" = sha256(jsonencode(kubernetes_config_map.sshpiper.data))
          "checksum/secrets" = sha256(jsonencode([
            kubernetes_secret.upstream_key.data,
            kubernetes_secret.resolver_db.data,
          ]))
        }
      }

      spec {
        automount_service_account_token = false

        service_account_name = kubernetes_service_account.sshpiper.metadata[0].name

        container {
          name  = "ssh-resolver"
          image = var.resolver_image

          env {
            name  = "CAELUS_SSH_RESOLVER_LISTEN"
            value = "127.0.0.1:${var.resolver_port}"
          }

          env {
            name  = "CAELUS_SSH_RESOLVER_UPSTREAM_KEY_PATH"
            value = "/upstreamkey/ssh_upstream_key"
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.resolver_db.metadata[0].name
            }
          }

          volume_mount {
            name       = "upstream-key"
            mount_path = "/upstreamkey/"
            read_only  = true
          }

          # Answered from a real query, not from the process being alive.
          readiness_probe {
            grpc {
              port = var.resolver_port
            }
            period_seconds    = 10
            timeout_seconds   = 3
            failure_threshold = 3
          }

          # Deliberately no liveness probe. A database outage must not restart
          # the process: restarting fixes nothing, and it would turn a
          # recoverable dependency failure into a CrashLoopBackOff that also
          # takes sshpiperd down with the pod.
          resources {
            requests = {
              cpu    = "10m"
              memory = "32Mi"
            }
            limits = {
              memory = "128Mi"
            }
          }
        }

        container {
          name  = "sshpiper"
          image = var.sshpiper_image

          # The wait is not belt-and-braces: sshpiperd calls ListCallbacks at
          # startup and exits fatally if the resolver is not answering yet, and
          # the kubelet starts containers in order without waiting for any of
          # them. Without this the edge loses that race on a cold start and
          # CrashLoopBackOffs its way to health, which is a poor way to learn
          # about it. A native sidecar (an init container with restartPolicy:
          # Always) would express this better, but the Kubernetes provider
          # pinned here has no `restart_policy` on `init_container`.
          command = ["/bin/sh", "-c"]
          args = [
            "until nc -z 127.0.0.1 ${var.resolver_port}; do sleep 0.2; done; exec /sshpiperd/sshpiperd grpc",
          ]

          port {
            container_port = 2222
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.sshpiper.metadata[0].name
            }
          }

          volume_mount {
            name       = "server-key"
            mount_path = "/serverkey/"
            read_only  = true
          }

          resources {
            requests = {
              cpu    = "10m"
              memory = "32Mi"
            }
            limits = {
              memory = "128Mi"
            }
          }
        }

        volume {
          name = "server-key"

          secret {
            secret_name = kubernetes_secret.server_key.metadata[0].name

            items {
              key  = "server_key"
              path = "ssh_host_ed25519_key"
            }
          }
        }

        volume {
          name = "upstream-key"

          secret {
            secret_name = kubernetes_secret.upstream_key.metadata[0].name

            items {
              key  = "ssh_upstream_key"
              path = "ssh_upstream_key"
            }
          }
        }
      }
    }
  }
}

# klipper ServiceLB binds var.ssh_port directly on the node (validated in the
# spike; no NodePort-range change needed). HAProxy on the homelab edge points
# its per-environment TCP frontend at this port.
resource "kubernetes_service" "sshpiper" {
  metadata {
    name      = "sshpiper"
    namespace = var.namespace
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "sshpiper"
    }

    port {
      name        = "ssh"
      protocol    = "TCP"
      port        = var.ssh_port
      target_port = 2222
    }
  }
}

output "upstream_public_key" {
  description = "Public half of this environment's upstream key, for the caelus-sftp chart"
  value       = trimspace(data.tls_public_key.upstream.public_key_openssh)
}
