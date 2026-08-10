module "oauth2-proxy" {
  source    = "./login"
  namespace = kubernetes_namespace.login.metadata[0].name
  domain    = local.domain

  # Select this workspace's Keycloak client. The clients themselves are
  # declared in tf/deps (the singleton root module); tf/app only chooses.
  oauth2_proxy_client_id     = var.oauth2_proxy_client_ids[terraform.workspace]
  oauth2_proxy_client_secret = var.oauth2_proxy_client_secrets[terraform.workspace]
  oauth2_proxy_cookie_secret = var.oauth2_proxy_cookie_secret

  # Dev is gated on Keycloak group membership; prod is open to anyone who has
  # registered. Registration is realm-level and the realm is shared, so this is
  # the only place the two environments can diverge on who gets in.
  allowed_groups = local.is_prod_workspace ? [] : ["freepod-dev"]
}

module "sshpiper" {
  source    = "./sshpiper"
  namespace = kubernetes_namespace.sshpiper.metadata[0].name
  ssh_port  = local.sshpiper_port
  rbac_name = "sshpiper-${local.ns_sshpiper}"
}

module "caelus" {
  source             = "./caelus"
  namespace          = kubernetes_namespace.caelus.metadata[0].name
  domain             = local.domain
  api_image          = local.api_image
  ui_image           = local.ui_image
  rbac_name          = "caelus-api-${kubernetes_namespace.caelus.metadata[0].name}"
  ns_login           = kubernetes_namespace.login.metadata[0].name
  db_password        = var.db_password
  wildcard_domains   = [local.domain]
  mollie_api_key     = var.mollie_api_key
  sshpiper_namespace = kubernetes_namespace.sshpiper.metadata[0].name
  sftp_host          = local.sftp_host
  sftp_port          = local.sftp_port

  depends_on = [kubernetes_namespace.caelus]
}
