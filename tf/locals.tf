locals {
  is_prod_workspace = terraform.workspace == "prod"

  ns_caelus = local.is_prod_workspace ? "caelus" : "caelus-dev"
  domain    = local.is_prod_workspace ? "app.deprutser.be" : "dev.deprutser.be"

  environment = var.environment != null ? var.environment : (
    local.is_prod_workspace ? "prod" : "dev"
  )

  # Cluster-scoped RBAC object names must be unique per deployment.
  rbac_name = "caelus-api-${local.ns_caelus}"
}
