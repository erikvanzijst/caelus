resource "kubernetes_namespace" "keycloak" {
  metadata {
    name = "keycloak"
  }
}

resource "kubernetes_namespace" "echo" {
  metadata {
    name = "echo"
  }
}

resource "kubernetes_namespace" "mailer" {
  metadata {
    name = "mailer"
  }
}

resource "kubernetes_namespace" "monitoring" {
  metadata {
    name = "monitoring"
  }
}

module "keycloak" {
  source                  = "./keycloak"
  namespace               = kubernetes_namespace.keycloak.metadata[0].name
  keycloak_admin_password = var.keycloak_admin_password
  keycloak_image          = var.keycloak_image
  domain                  = "freepod.eu"
}

module "certmanager" {
  source               = "./certmanager"
  cloudflare_api_token = var.cloudflare_api_token
  letsencrypt_email    = var.letsencrypt_email
}

module "system" {
  source          = "./system"
  haproxy_edge_ip = var.haproxy_edge_ip

  # Traefik's default cert store points at the wildcard secret cert-manager issues.
  depends_on = [module.certmanager]
}

module "sshpiper_crd" {
  source = "./sshpiper"
}

module "mailer" {
  source        = "./mailer"
  namespace     = kubernetes_namespace.mailer.metadata[0].name
  smtp_host     = var.smtp_host
  smtp_port     = var.smtp_port
  smtp_username = var.smtp_username
  smtp_password = var.smtp_password
}

# --- Monitoring stack (cluster-wide observability) ---

module "loki" {
  source    = "./loki"
  namespace = kubernetes_namespace.monitoring.metadata[0].name
}

module "prometheus" {
  source                     = "./prometheus"
  namespace                  = kubernetes_namespace.monitoring.metadata[0].name
  grafana_admin_password     = var.grafana_admin_password
  alert_email_to             = var.alert_email_to
  grafana_oidc_client_id     = var.grafana_oidc_client_id
  grafana_oidc_client_secret = var.grafana_oidc_client_secret

  # Alertmanager delivers via the in-cluster mailer relay.
  depends_on = [module.mailer]
}
