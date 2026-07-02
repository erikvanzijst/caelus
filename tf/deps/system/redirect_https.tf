# HTTP->HTTPS redirect for freepod (task 5.8 — replaces the entrypoint redirect that
# deadlocked HTTP-01; see traefik.tf). A web-only, lowest-priority catch-all
# IngressRoute + a redirectScheme Middleware. Two properties make it correct:
#
#   - It lives on the `web` entrypoint ONLY, so it never touches websecure traffic
#     (no redirect loop). App Ingresses are rendered websecure-only (products/*/chart)
#     so their plain-HTTP :80 traffic falls through to this redirect.
#   - It is the lowest priority, so cert-manager's HTTP-01 solver Ingress (a longer,
#     exact /.well-known/acme-challenge/<token> rule) out-ranks it and ACME challenges
#     are still served as plain HTTP on :80 (validated live).
#
# redirectScheme targets `https://<host>` with no port, which also avoids the internal
# :8443 leak the entrypoint redirect produced.
resource "kubernetes_manifest" "redirect_https_middleware" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "Middleware"
    metadata = {
      name      = "redirect-https"
      namespace = "kube-system"
    }
    spec = {
      redirectScheme = {
        scheme    = "https"
        permanent = true
      }
    }
  }

  # The traefik.io/v1alpha1 CRDs are installed by the Traefik Helm release.
  depends_on = [module.traefik]
}

resource "kubernetes_manifest" "redirect_https_route" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "IngressRoute"
    metadata = {
      name      = "http-to-https"
      namespace = "kube-system"
    }
    spec = {
      entryPoints = ["web"]
      routes = [{
        match    = "PathPrefix(`/`)"
        kind     = "Rule"
        priority = 1
        middlewares = [{
          name = "redirect-https"
        }]
        # redirectScheme short-circuits with a 301 before the service is used; the
        # traefik service is a never-hit placeholder (IngressRoute requires one).
        services = [{
          name = "traefik"
          port = 80
        }]
      }]
    }
  }

  depends_on = [kubernetes_manifest.redirect_https_middleware]
}
