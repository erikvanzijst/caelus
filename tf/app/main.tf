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

  # This environment's upstream credential.
  upstream_private_key = var.sshpiper_upstream_private_keys[terraform.workspace]

  resolver_image = var.ssh_resolver_image

  resolver_database_url = format(
    "postgresql://%s:%s@%s:5432/%s",
    module.caelus.ssh_resolver_db_role,
    module.caelus.ssh_resolver_db_password,
    module.caelus.database_host,
    module.caelus.database_name,
  )
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
  builds_namespace   = kubernetes_namespace.builds.metadata[0].name
  builder_image      = var.builder_image
  sftp_host          = local.sftp_host
  sftp_port          = local.sftp_port

  # Select this workspace's Garage bucket and key. Like the Keycloak clients
  # above, the buckets and keys themselves are created in tf/deps (the singleton
  # root module); tf/app only chooses which pair this environment gets.
  s3_endpoint_url      = var.s3_endpoint_url
  s3_region            = var.s3_region
  s3_bucket            = var.s3_buckets[terraform.workspace]
  s3_access_key_id     = var.s3_access_key_ids[terraform.workspace]
  s3_secret_access_key = var.s3_secret_access_keys[terraform.workspace]

  garage_admin_url   = var.garage_admin_url
  garage_admin_token = var.garage_admin_token

  # Per workspace, like the Garage key above and for the same reason: a dev key
  # must not decrypt a prod tenant's secrets. Defaults to empty so a workspace
  # that has not been given one still plans -- legal only while no product
  # template declares vars.
  var_encryption_keys = lookup(var.var_encryption_keys, terraform.workspace, [])

  # Loki, like Garage above, is a tf/deps singleton shared by both workspaces.
  loki_base_url         = var.loki_base_url
  log_keepalive_seconds = var.log_keepalive_seconds

  depends_on = [kubernetes_namespace.caelus, kubernetes_namespace.builds]
}
