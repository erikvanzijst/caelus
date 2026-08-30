# The SSH auth resolver's database credential and the bootstrap that creates it.
#
# The resolver itself does not live here -- it runs as a sidecar in the
# sshpiperd pod, in the SSH edge's own namespace (tf/app/sshpiper). Only its
# role belongs with the database, and only the platform database knows how to
# create it.
#
# `special = false` for the same reason as the tenant passwords: this ends up in
# a libpq URL, and a password that needs percent-encoding is a bug waiting for
# the one character that gets it wrong.
resource "random_password" "ssh_resolver_db" {
  length  = 32
  special = false
}

# Read by the bootstrap init container, which sets it on the role. The
# resolver's own copy is assembled in tf/app/sshpiper from the output below --
# a Secret in this namespace is not reachable from the edge's.
resource "kubernetes_secret" "ssh_resolver_db_bootstrap" {
  metadata {
    name      = "caelus-ssh-resolver-db"
    namespace = var.namespace
  }

  type = "Opaque"

  data = {
    SSH_RESOLVER_PASSWORD = random_password.ssh_resolver_db.result
  }
}

# A ConfigMap rather than an image layer, for the same reason as the tenant
# bootstrap: the script has to be editable and re-appliable without rebuilding
# anything, and a checksum annotation on the consuming pod makes an edit land.
resource "kubernetes_config_map" "ssh_resolver_bootstrap" {
  metadata {
    name      = "caelus-ssh-resolver-bootstrap"
    namespace = var.namespace
  }

  data = {
    "ssh-resolver-bootstrap.sql" = file("${path.module}/ssh-resolver-bootstrap.sql")
  }
}
