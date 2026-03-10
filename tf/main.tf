terraform {
  required_version = ">= 1.0"
}

module "keycloak" {
  source                     = "./keycloak"
  namespace                  = kubernetes_namespace.keycloak.metadata[0].name
  keycloak_admin_password    = var.keycloak_admin_password
  domain                     = "app.deprutser.be"
}

module "oauth2-proxy" {
  source                     = "./login"
  namespace                  = kubernetes_namespace.login.metadata[0].name
  domain                     = local.domain
  oauth2_proxy_client_secret = var.oauth2_proxy_client_secret
  oauth2_proxy_cookie_secret = var.oauth2_proxy_cookie_secret
}

module "echo" {
  source    = "./echo"
  namespace = kubernetes_namespace.echo.metadata[0].name
  domain    = local.domain
}

module "caelus" {
  source      = "./caelus"
  namespace   = kubernetes_namespace.caelus.metadata[0].name
  domain      = local.domain
  api_image   = var.api_image
  ui_image    = var.ui_image
  rbac_name   = "caelus-api-${kubernetes_namespace.caelus.metadata[0].name}"
  ns_login    = kubernetes_namespace.login.metadata[0].name
  db_password = var.db_password

  depends_on = [kubernetes_namespace.caelus]
}
