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

    # Builds. The namespace is per environment, so it must come from here
    # rather than the code default (which is the prod name). The in-flight
    # limit is here because it is an operational knob — tuning it should not
    # need an API image rebuild.
    CAELUS_BUILDS_NAMESPACE    = var.builds_namespace
    CAELUS_BUILD_MAX_IN_FLIGHT = tostring(var.build_max_in_flight)

    # CAELUS_LOG_LEVEL    = "info"
    PYTHONUNBUFFERED    = "1"

    # Trust X-Forwarded-For/Proto from the in-cluster Traefik pod so uvicorn
    # reports the real client IP instead of the proxy's pod IP. Value is the
    # k3s pod CIDR; uvicorn walks the XFF chain in reverse and returns the
    # first host outside this range.
    FORWARDED_ALLOW_IPS = "10.42.0.0/16"
  }
}
