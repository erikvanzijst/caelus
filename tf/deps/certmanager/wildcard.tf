# Wildcard certificate for *.freepod.eu / *.dev.freepod.eu, issued via DNS-01 and
# stored in Traefik's namespace so it can be used as the default certificate store
# (see tf/deps/system/traefik.tf). Mirrors the homelab certs/certificate.tf pattern.
#
# Switch issuerRef.name to `letsencrypt-dns-staging` during rollout to avoid
# burning Let's Encrypt production quota, then back to `letsencrypt-dns`.
resource "kubernetes_manifest" "wildcard_freepod_eu" {
  manifest = {
    apiVersion = "cert-manager.io/v1"
    kind       = "Certificate"
    metadata = {
      name      = "wildcard-freepod-eu"
      namespace = var.traefik_namespace
    }
    spec = {
      secretName = "wildcard-freepod-eu-tls"

      issuerRef = {
        name = "letsencrypt-dns"
        kind = "ClusterIssuer"
      }

      commonName = "*.freepod.eu"

      dnsNames = [
        "freepod.eu",
        "*.freepod.eu",
        "*.dev.freepod.eu",
      ]
    }
  }

  depends_on = [
    kubernetes_manifest.letsencrypt_dns,
  ]
}

output "wildcard_secret_name" {
  description = "Name of the *.freepod.eu wildcard TLS secret (in the Traefik namespace) for the default cert store."
  value       = "wildcard-freepod-eu-tls"
}
