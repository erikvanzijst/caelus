module "oauth2-proxy" {
  source                     = "./login"
  namespace                  = kubernetes_namespace.login.metadata[0].name
  domain                     = local.domain
  oauth2_proxy_client_secret = var.oauth2_proxy_client_secret
  oauth2_proxy_cookie_secret = var.oauth2_proxy_cookie_secret
}

module "sshpiper" {
  source    = "./sshpiper"
  namespace = kubernetes_namespace.sshpiper.metadata[0].name
  ssh_port  = local.sshpiper_port
  rbac_name = "sshpiper-${local.ns_sshpiper}"
}

module "caelus" {
  source         = "./caelus"
  namespace      = kubernetes_namespace.caelus.metadata[0].name
  domain         = local.domain
  api_image      = var.api_image
  ui_image       = var.ui_image
  rbac_name      = "caelus-api-${kubernetes_namespace.caelus.metadata[0].name}"
  ns_login       = kubernetes_namespace.login.metadata[0].name
  db_password    = var.db_password
  wildcard_domains = [local.domain]
  mollie_api_key = var.mollie_api_key
  sshpiper_namespace = kubernetes_namespace.sshpiper.metadata[0].name
  sftp_host = local.sftp_host
  sftp_port = local.sftp_port

  depends_on = [kubernetes_namespace.caelus]
}
