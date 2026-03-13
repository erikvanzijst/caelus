resource "kubernetes_config_map" "api" {
  metadata {
    name      = "caelus-api-config"
    namespace = var.namespace
  }

  data = {
    CAELUS_DATABASE_URL = "postgresql+psycopg://${var.db_user}:${var.db_password}@caelus-postgres:5432/${var.db_name}"
    # CAELUS_DATABASE_URL = "sqlite:////app/db/caelus.db"
    # CAELUS_LOG_LEVEL    = "info"
    PYTHONUNBUFFERED     = "1"
  }
}
