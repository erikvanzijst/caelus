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
              name = kubernetes_service.echo_proxy.metadata[0].name
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

resource "kubernetes_endpoints" "echo_proxy" {
  metadata {
    # Must match the service name for Kubernetes to associate them.
    name      = kubernetes_service.echo_proxy.metadata[0].name
    namespace = var.namespace
  }

  subset {
    address {
      ip = data.kubernetes_service.echo.spec[0].cluster_ip
    }

    port {
      port = 8080
    }
  }
}
