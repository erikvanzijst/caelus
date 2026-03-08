resource "kubernetes_ingress_v1" "keycloak" {
  metadata {
    name      = "keycloak"
    namespace = var.namespace
    # annotations = {
    #   "traefik.ingress.kubernetes.io/router.entrypoints" = "websecure"
    # }
  }

  spec {
    # tls {
    #   hosts = ["keycloak.${var.domain}"]
    # }

    rule {
      host = "keycloak.${var.domain}"

      http {
        path {
          path      = "/"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.keycloak.metadata[0].name

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
