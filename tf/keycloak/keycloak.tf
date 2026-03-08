resource "kubernetes_secret" "keycloak" {
  metadata {
    name      = "keycloak-db-secret"
    namespace = var.namespace
  }

  type = "Opaque"

  data = {
    KC_PROXY                       = "edge"
    KC_PROXY_ADDRESS_FORWARDING    = "true"
    KC_HOSTNAME_STRICT             = "false"
    KC_HOSTNAME_STRICT_BACKCHANNEL = "false"
    KC_HOSTNAME_URL                = "https://keycloak.${var.domain}"
    KC_HOSTNAME_ADMIN_URL          = "https://keycloak.${var.domain}"
    KC_LOG_LEVEL                   = "DEBUG"
    KC_DB                          = "postgres"
    KC_DB_URL                      = "jdbc:postgresql://${kubernetes_service.postgres.metadata[0].name}.${var.namespace}.svc.cluster.local:5432/keycloak"
    KC_DB_USERNAME                 = "keycloak"
    KC_DB_PASSWORD                 = "keycloak"
    KEYCLOAK_ADMIN                 = "admin"
    KEYCLOAK_ADMIN_PASSWORD        = var.keycloak_admin_password
  }
}

resource "kubernetes_deployment" "keycloak" {
  metadata {
    name      = "keycloak"
    namespace = var.namespace
    labels = {
      app = "keycloak"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "keycloak"
      }
    }

    template {
      metadata {
        labels = {
          app = "keycloak"
        }
      }

      spec {
        container {
          name  = "keycloak"
          image = "quay.io/keycloak/keycloak:24.0"

          args = ["start", "--hostname-debug=true"]

          port {
            container_port = 8080
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.keycloak.metadata[0].name
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "keycloak" {
  metadata {
    name      = "keycloak"
    namespace = var.namespace
  }

  spec {
    selector = {
      app = "keycloak"
    }

    port {
      port        = 80
      target_port = 8080
    }
  }
}
