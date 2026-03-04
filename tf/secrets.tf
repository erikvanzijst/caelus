resource "kubernetes_secret" "db" {
  metadata {
    name      = "caelus-db"
    namespace = local.namespace
  }

  type = "Opaque"

  data = {
    username = var.db_user
    password = var.db_password
    database = var.db_name
  }

  depends_on = [kubernetes_namespace.main]
}
