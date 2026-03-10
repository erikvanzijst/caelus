resource "kubernetes_deployment" "echo" {
  metadata {
    name      = "echo"
    namespace = var.namespace
    labels = {
      app = "echo"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "echo"
      }
    }

    template {
      metadata {
        labels = {
          app = "echo"
        }
      }

      spec {
        container {
          name  = "echo"
          image = "mendhak/http-https-echo"

          port {
            container_port = 8080
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "echo" {
  metadata {
    name      = "echo"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "echo"
    }

    port {
      port        = 8080
      target_port = 8080
    }
  }
}

resource "kubernetes_ingress_v1" "echo" {
  metadata {
    name      = "echo"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class"                         = "traefik"
      # "traefik.ingress.kubernetes.io/router.entrypoints" = "websecure"
    }
  }

  spec {
    rule {
      host = "echo.${var.domain}"

      http {
        path {
          path      = "/"
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
      }
    }
  }
}
