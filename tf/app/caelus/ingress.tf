# Webhook endpoints bypass oauth2-proxy entirely — Mollie (and future
# providers) POST here without auth cookies, so no forward-auth middleware.
resource "kubernetes_ingress_v1" "webhooks" {
  metadata {
    name      = "caelus-webhooks-ingress"
    namespace = var.namespace

    annotations = {
      "traefik.ingress.kubernetes.io/router.entrypoints" = "web, websecure"
    }
  }

  spec {
    rule {
      host = var.domain

      http {
        path {
          path      = "/api/webhooks"
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
      }
    }
  }
}

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
          path      = "/echo"
          path_type = "Prefix"

          backend {
            service {
              name = kubernetes_service.echo.metadata[0].name
              port {
                number = 8080
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

resource "kubernetes_service" "echo_proxy" {
  metadata {
    name      = "echo-proxy"
    namespace = var.namespace
  }

  spec {
    # No selector — routes to the echo service in the echo namespace
    # via the manually-defined Endpoints resource below.
    port {
      port        = 8080
      target_port = 8080
    }
  }
}

data "kubernetes_service" "echo" {
  metadata {
    name      = "echo"
    namespace = "echo"
  }
}
