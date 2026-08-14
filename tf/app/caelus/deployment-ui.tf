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
          image             = var.ui_image
          image_pull_policy = "Always"
          name              = "ui"

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
  # Ignore restartedAt annotations written by `kubectl rollout restart`
  lifecycle {
    ignore_changes = [
      spec[0].template[0].metadata[0].annotations["kubectl.kubernetes.io/restartedAt"],
    ]
  }
}
