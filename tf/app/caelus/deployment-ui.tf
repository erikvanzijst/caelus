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
        # Roll the deployment whenever the rendered config.js changes. subPath
        # mounts don't live-update, so a content change needs a fresh pod.
        annotations = {
          "caelus/config-hash" = sha256(kubernetes_config_map.ui.data["config.js"])
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

          volume_mount {
            name       = "ui-config"
            mount_path = "/usr/share/nginx/html/config.js"
            sub_path   = "config.js"
            read_only  = true
          }
        }

        volume {
          name = "ui-config"
          config_map {
            name = kubernetes_config_map.ui.metadata[0].name
          }
        }
      }
    }
  }
}
