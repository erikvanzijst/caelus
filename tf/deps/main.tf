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

resource "kubernetes_namespace" "mailer" {
  metadata {
    name = "mailer"
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

module "mailer" {
  source = "./mailer"
  namespace = kubernetes_namespace.mailer.metadata[0].name
  smtp_host = var.smtp_host
  smtp_port = var.smtp_port
  smtp_username = var.smtp_username
  smtp_password = var.smtp_password
}
