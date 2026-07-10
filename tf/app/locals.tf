locals {
  is_prod_workspace = terraform.workspace == "prod"

  ns_caelus = local.is_prod_workspace ? "caelus" : "caelus-dev"
  domain    = local.is_prod_workspace ? "freepod.eu" : "dev.freepod.eu"

  environment = var.environment != null ? var.environment : (
    local.is_prod_workspace ? "prod" : "dev"
  )

  # Cluster-scoped RBAC object names must be unique per deployment.
  rbac_name = "caelus-api-${local.ns_caelus}"

  # SFTP entry point (see the sftp-file-access OpenSpec change). The cluster
  # port is what klipper ServiceLB binds on the node and the homelab HAProxy
  # dials; internal hops avoid 22 because the hosts' own sshd lives there.
  ns_sshpiper = local.is_prod_workspace ? "sshpiper" : "sshpiper-dev"
  sshpiper_port = var.sshpiper_port != null ? var.sshpiper_port : (
    local.is_prod_workspace ? 2222 : 2223
  )
}
