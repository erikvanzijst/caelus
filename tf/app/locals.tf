locals {
  is_prod_workspace = terraform.workspace == "prod"

  ns_caelus = local.is_prod_workspace ? "caelus" : "caelus-dev"
  domain    = local.is_prod_workspace ? "freepod.eu" : "dev.freepod.eu"

  environment = var.environment != null ? var.environment : (
    local.is_prod_workspace ? "prod" : "dev"
  )

  # Cluster-scoped RBAC object names must be unique per deployment.
  rbac_name = "caelus-api-${local.ns_caelus}"

  # Container images track a moving tag per environment: prod rolls to :master
  # (published by scripts/build-images.sh as the branch tag), dev to :latest.
  # var.api_image/var.ui_image override for pinning a specific SHA (rollback).
  image_tag = local.is_prod_workspace ? "master" : "latest"
  api_image = var.api_image != null ? var.api_image : "ghcr.io/erikvanzijst/caelus/api:${local.image_tag}"
  ui_image  = var.ui_image != null ? var.ui_image : "ghcr.io/erikvanzijst/caelus/ui:${local.image_tag}"

  # Per-build Kubernetes Jobs run here, one namespace per environment. Shared
  # would have no Terraform owner (each workspace has its own state, so the
  # second apply collides and a dev destroy would take prod's with it) and
  # would let the dev build worker delete prod's build Jobs, since the worker's
  # Role is namespaced and it deletes Jobs as its deadline backstop.
  ns_builds = local.is_prod_workspace ? "caelus-builds" : "caelus-builds-dev"

  # SFTP entry point (see the sftp-file-access OpenSpec change). The cluster
  # port is what klipper ServiceLB binds on the node and the homelab HAProxy
  # dials; internal hops avoid 22 because the hosts' own sshd lives there.
  ns_sshpiper = local.is_prod_workspace ? "sshpiper" : "sshpiper-dev"
  sshpiper_port = var.sshpiper_port != null ? var.sshpiper_port : (
    local.is_prod_workspace ? 2222 : 2223
  )

  # User-facing SFTP endpoint the API/UI advertise: the public router values
  # (not the internal HAProxy/cluster ports). prod freepod.eu:22, dev
  # dev.freepod.eu:23.
  sftp_host = local.domain
  sftp_port = local.is_prod_workspace ? 22 : 23
}
