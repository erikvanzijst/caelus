terraform {
  required_version = ">= 1.0"
}

module "keycloak" {
  source                     = "./keycloak"
  namespace                  = kubernetes_namespace.keycloak.metadata[0].name
  keycloak_admin_password    = var.keycloak_admin_password
  domain                     = "app.deprutser.be"
}

# module "oauth2-proxy" {
#   source                     = "./oauth2-proxy"
#   namespace                  = kubernetes_namespace.oauth2-proxy.metadata[0].name
#   domain                     = "app.deprutser.be"
#   oauth2_proxy_client_secret = var.oauth2_proxy_client_secret
#   oauth2_proxy_cookie_secret = var.oauth2_proxy_cookie_secret
# }
