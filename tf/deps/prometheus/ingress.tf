# Grafana is the ONLY externally exposed monitoring UI. Prometheus and
# Alertmanager stay ClusterIP (reach them via `kubectl port-forward`).
#
# Deliberately NO forward-auth middleware: Grafana performs its own Keycloak
# OIDC login (grafana.tf).
resource "kubernetes_ingress_v1" "grafana" {
  metadata {
    name      = "grafana"
    namespace = var.namespace
    annotations = {
      "kubernetes.io/ingress.class" = "traefik"
    }
  }

  spec {
    rule {
      host = var.grafana_domain
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "grafana"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.grafana]
}
