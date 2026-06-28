# Cloudflare API token used by the DNS-01 solver. Lives in the cert-manager
# namespace (created by the helm_release).
resource "kubernetes_secret" "cloudflare_api_token" {
  metadata {
    name      = "cloudflare-api-token-secret"
    namespace = "cert-manager"
  }

  data = {
    api-token = var.cloudflare_api_token
  }

  type = "Opaque"

  depends_on = [helm_release.cert_manager]
}

# DNS-01 (Cloudflare) issuer — used for the *.freepod.eu wildcard. We control
# freepod.eu DNS on Cloudflare, so DNS-01 avoids per-app HTTP-01 round-trips and
# keeps the freepod.eu registered domain off the HTTP-01 rate-limit path.
resource "kubernetes_manifest" "letsencrypt_dns" {
  manifest = yamldecode(<<-EOF
    apiVersion: cert-manager.io/v1
    kind: ClusterIssuer
    metadata:
      name: letsencrypt-dns
    spec:
      acme:
        email: "${var.letsencrypt_email}"
        server: https://acme-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          name: letsencrypt-dns-account-key
        solvers:
          - dns01:
              cloudflare:
                apiTokenSecretRef:
                  name: ${kubernetes_secret.cloudflare_api_token.metadata[0].name}
                  key: api-token
            selector:
              dnsZones:
                - freepod.eu
  EOF
  )

  depends_on = [helm_release.cert_manager]
}

resource "kubernetes_manifest" "letsencrypt_dns_staging" {
  manifest = yamldecode(<<-EOF
    apiVersion: cert-manager.io/v1
    kind: ClusterIssuer
    metadata:
      name: letsencrypt-dns-staging
    spec:
      acme:
        email: "${var.letsencrypt_email}"
        server: https://acme-staging-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          name: letsencrypt-dns-staging-account-key
        solvers:
          - dns01:
              cloudflare:
                apiTokenSecretRef:
                  name: ${kubernetes_secret.cloudflare_api_token.metadata[0].name}
                  key: api-token
            selector:
              dnsZones:
                - freepod.eu
  EOF
  )

  depends_on = [helm_release.cert_manager]
}

# HTTP-01 (Traefik ingress class) issuer — used per-app for custom domains, where
# DNS-01 is impossible (the user owns their domain's DNS). The challenge is served
# on :80 via the HAProxy edge default backend.
resource "kubernetes_manifest" "letsencrypt_http" {
  manifest = yamldecode(<<-EOF
    apiVersion: cert-manager.io/v1
    kind: ClusterIssuer
    metadata:
      name: letsencrypt-http
    spec:
      acme:
        email: "${var.letsencrypt_email}"
        server: https://acme-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          name: letsencrypt-http-account-key
        solvers:
          - http01:
              ingress:
                class: traefik
  EOF
  )

  depends_on = [helm_release.cert_manager]
}

resource "kubernetes_manifest" "letsencrypt_http_staging" {
  manifest = yamldecode(<<-EOF
    apiVersion: cert-manager.io/v1
    kind: ClusterIssuer
    metadata:
      name: letsencrypt-http-staging
    spec:
      acme:
        email: "${var.letsencrypt_email}"
        server: https://acme-staging-v02.api.letsencrypt.org/directory
        privateKeySecretRef:
          name: letsencrypt-http-staging-account-key
        solvers:
          - http01:
              ingress:
                class: traefik
  EOF
  )

  depends_on = [helm_release.cert_manager]
}
