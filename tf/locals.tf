locals {
  is_prod_workspace = terraform.workspace == "prod"

  default_namespace = local.is_prod_workspace ? "caelus" : "caelus-dev"
  default_domain    = local.is_prod_workspace ? "app.deprutser.be" : "dev.deprutser.be"

  namespace = var.namespace != null ? var.namespace : local.default_namespace
  domain    = var.domain != null ? var.domain : local.default_domain
  environment = var.environment != null ? var.environment : (
    local.is_prod_workspace ? "production" : "development"
  )

  # Cluster-scoped RBAC object names must be unique per deployment.
  rbac_name = "caelus-api-${local.namespace}"
}
