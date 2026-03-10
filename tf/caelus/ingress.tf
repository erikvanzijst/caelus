resource "kubernetes_ingress_v1" "caelus" {
  metadata {
    name      = "caelus-ingress"
    namespace = var.namespace

    annotations = {
      "traefik.ingress.kubernetes.io/router.entrypoints" = "web, websecure"
      "traefik.ingress.kubernetes.io/router.middlewares" = "${var.ns_login}-oauth-errors@kubernetescrd, ${var.ns_login}-forward-auth@kubernetescrd"
    }
  }

  spec {
    rule {
      host = var.domain

      http {
        path {
          path      = "/api"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.api.metadata[0].name
              port {
                number = 8000
              }
            }
          }
        }

        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.ui.metadata[0].name
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}
