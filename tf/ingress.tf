resource "kubernetes_ingress" "main" {
  metadata {
    name      = "caelus-ingress"
    namespace = var.namespace

    annotations = {
      "kubernetes.io/ingress.class"                  = "traefik"
      "traefik.ingress.kubernetes.io/rewrite-target" = "/"
    }
  }

  spec {
    ingress_class_name = "traefik"

    rule {
      host = var.domain
      http {
        path {
          path = "/api"
          backend {
            service_name = "caelus-api"
            service_port = 8000
          }
        }

        path {
          path = "/"
          backend {
            service_name = "caelus-ui"
            service_port = 80
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_namespace.main,
    kubernetes_service.api,
    kubernetes_service.ui
  ]
}
