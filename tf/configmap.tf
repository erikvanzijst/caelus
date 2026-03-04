resource "kubernetes_config_map" "api" {
  metadata {
    name      = "caelus-api-config"
    namespace = local.namespace
  }

  data = {
    DATABASE_URL     = "postgresql+psycopg://${var.db_user}:${var.db_password}@caelus-postgres:5432/${var.db_name}"
    # DATABASE_URL     = "sqlite:////app/db/caelus.db"
    # LOG_LEVEL        = "info"
    PYTHONUNBUFFERED = "1"
  }

  depends_on = [kubernetes_namespace.main]
}
