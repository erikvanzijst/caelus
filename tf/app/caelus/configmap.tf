resource "kubernetes_config_map" "api" {
  metadata {
    name      = "caelus-api-config"
    namespace = var.namespace
  }

  data = {
    CAELUS_BASE_URL = "https://${var.domain}"
    CAELUS_BASE_URL_API = "https://${var.domain}/api/"
    CAELUS_STATIC_PATH  = "/var/static"
    CAELUS_DATABASE_URL = "postgresql+psycopg://${var.db_user}:${var.db_password}@caelus-postgres:5432/${var.db_name}"
    CAELUS_LB_IPS = jsonencode(var.lb_ips)
    CAELUS_WILDCARD_DOMAINS = jsonencode(var.wildcard_domains)
    # CAELUS_LOG_LEVEL    = "info"
    PYTHONUNBUFFERED    = "1"
  }
}
