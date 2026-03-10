resource "kubernetes_namespace" "main" {
  metadata {
    name = local.namespace

    labels = {
      name        = local.namespace
      environment = local.environment
    }
  }
}

resource "kubernetes_namespace" "keycloak" {
  metadata {
    name = "keycloak"
  }
}

resource "kubernetes_namespace" "oauth2-proxy" {
  metadata {
    name = "oauth2-proxy"
  }
}

resource "kubernetes_namespace" "auth_system" {
  metadata {
    name = "auth-system"

    labels = {
      name        = "auth-system"
      environment = local.environment
    }
  }
}

resource "kubernetes_namespace" "echo" {
  metadata {
    name = "echo"
  }
}
