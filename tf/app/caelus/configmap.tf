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
    CAELUS_DOMAIN = var.domain
    CAELUS_WILDCARD_DOMAINS = jsonencode(var.wildcard_domains)
    CAELUS_MOLLIE_API_KEY = var.mollie_api_key
    CAELUS_MOLLIE_REDIRECT_URL="https://${var.domain}"
    CAELUS_MOLLIE_WEBHOOK_BASE_URL="https://${var.domain}/api/"
    CAELUS_SSHPIPER_NAMESPACE = var.sshpiper_namespace
    CAELUS_SFTP_HOST = var.sftp_host
    CAELUS_SFTP_PORT = tostring(var.sftp_port)

    # CAELUS_LOG_LEVEL    = "info"
    PYTHONUNBUFFERED    = "1"
  }
}
