resource "kubernetes_ingress_v1" "main" {
  metadata {
    name      = "caelus-ingress"
    namespace = local.namespace

    # annotations = {
    #   "traefik.ingress.kubernetes.io/router.middlewares": "oauth2-proxy-forward-auth@kubernetescrd"
    # }
  }

  spec {
    ingress_class_name = "traefik"

    rule {
      host = local.domain

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

  depends_on = [kubernetes_namespace.main]
}
