# Per-environment sshpiperd: the single SSH entry point for tenant SFTP
# access. Routes connections by username to per-deployment atmoz/sftp
# sidecars via Pipe CRs (CRD installed by tf/deps/sshpiper), watched
# cluster-wide. Environment separation is enforced by the tenant baseline
# NetworkPolicy, which only admits this environment's proxy pods.
#
# Validated by a spike on the dev cluster (see the sftp-file-access OpenSpec
# change for findings, e.g. why ignore_hostkey stays required).

# Stable host key: clients' known_hosts entries must survive pod restarts
# and redeploys. Lives in Terraform state like the platform's other secrets.
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
    PLUGIN                              = "kubernetes"
    SSHPIPERD_KUBERNETES_ALL_NAMESPACES = "true"
    SSHPIPERD_SERVER_KEY                = "/serverkey/ssh_host_ed25519_key"
    SSHPIPERD_LOG_LEVEL                 = "info"

    # Drop the upstream sidecar's hostkeys-00@openssh.com advertisement so the
    # OpenSSH client does not attempt (and fail) host-key rotation across the
    # proxy -- the "server gave bad signature" warning. Opt-in because it
    # disables OpenSSH's host-key-rotation guard, which is intended here: the
    # client should only ever pin sshpiper's stable key, never the sidecars'
    # ephemeral keys. (tg123/sshpiper#131, PR #140.)
    SSHPIPERD_DROP_HOSTKEYS_MESSAGE = "true"
  }
}

# Pipes live in tenant namespaces, so the watch is cluster-scoped.
resource "kubernetes_cluster_role" "sshpiper" {
  metadata {
    name = var.rbac_name
  }

  rule {
    api_groups = ["sshpiper.com"]
    resources  = ["pipes"]
    verbs      = ["get", "list", "watch"]
  }

  # Pipe fields may reference Secrets (private_key_secret, password_secret).
  rule {
    api_groups = [""]
    resources  = ["secrets"]
    verbs      = ["get"]
  }
}

resource "kubernetes_cluster_role_binding" "sshpiper" {
  metadata {
    name = var.rbac_name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.sshpiper.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.sshpiper.metadata[0].name
    namespace = var.namespace
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
        }
      }

      spec {
        service_account_name = kubernetes_service_account.sshpiper.metadata[0].name

        container {
          name  = "sshpiper"
          image = var.sshpiper_image

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
