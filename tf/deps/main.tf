resource "kubernetes_namespace" "keycloak" {
  metadata {
    name = "keycloak"
  }
}

resource "kubernetes_namespace" "echo" {
  metadata {
    name = "echo"
  }
}

module "keycloak" {
  source                  = "./keycloak"
  namespace               = kubernetes_namespace.keycloak.metadata[0].name
  keycloak_admin_password = var.keycloak_admin_password
  domain                  = "app.deprutser.be"
}

module "system" {
  source = "./system"
}
