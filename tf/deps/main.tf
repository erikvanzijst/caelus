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
  keycloak_image          = var.keycloak_image
  domain                  = "freepod.eu"
}

module "certmanager" {
  source               = "./certmanager"
  cloudflare_api_token = var.cloudflare_api_token
  letsencrypt_email    = var.letsencrypt_email
}

module "system" {
  source          = "./system"
  haproxy_edge_ip = var.haproxy_edge_ip

  # Traefik's default cert store points at the wildcard secret cert-manager issues.
  depends_on = [module.certmanager]
}

module "sshpiper_crd" {
  source = "./sshpiper"
}

module "mailer" {
  source = "./mailer"
  namespace = kubernetes_namespace.mailer.metadata[0].name
  smtp_host = var.smtp_host
  smtp_port = var.smtp_port
  smtp_username = var.smtp_username
  smtp_password = var.smtp_password
}
