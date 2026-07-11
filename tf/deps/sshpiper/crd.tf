# Cluster-scoped Pipe CRD for sshpiper (SSH reverse proxy used for tenant
# SFTP access). Shared singleton: the per-environment sshpiperd deployments
# live in tf/app and consume this CRD.
#
# crd.yaml is vendored from the pinned upstream release so the schema always
# matches the sshpiperd image version deployed by tf/app:
# https://raw.githubusercontent.com/tg123/sshpiper/v1.5.4/plugin/kubernetes/crd.yaml
resource "kubernetes_manifest" "pipe_crd" {
  manifest = yamldecode(file("${path.module}/crd.yaml"))
}
