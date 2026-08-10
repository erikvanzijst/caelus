# https://junwu.shouyicheng.com/posts/keycloak-oauth2-proxy-secure-web-application/
#
resource "helm_release" "oauth2_proxy" {
  name             = "oauth2-proxy"
  repository       = "https://oauth2-proxy.github.io/manifests"
  chart            = "oauth2-proxy"
  version          = "10.1.4"
  namespace        = var.namespace
  create_namespace = false

  values = [
    yamlencode({
      replicaCount = 1
      config = {
        clientID     = var.oauth2_proxy_client_id
        clientSecret = var.oauth2_proxy_client_secret
        cookieSecret = var.oauth2_proxy_cookie_secret
        configFile   = <<-EOT
          email_domains = ["*"]
          ${length(var.allowed_groups) > 0 ? "allowed_groups = ${jsonencode(var.allowed_groups)}" : "# allowed_groups: unset — no group restriction in this environment"}
          upstreams = ["file:///dev/null"]
          cookie_secure = false
          # No cookie_domains: the cookie is issued host-only by the apex
          # callback (${var.domain}) and is therefore never sent to wildcard
          # user-app subdomains. whitelist_domains still guards rd= redirects.
          whitelist_domains = ["${var.domain}"]
          provider = "keycloak-oidc"
          # Routes allowed through WITHOUT a session. forward-auth returns 202
          # for these so the request reaches the (already-public) API/UI.
          #
          # FOOTGUN: skip-auth bypasses oauth2-proxy entirely, so it neither
          # injects nor sanitizes X-Auth-Request-Email on these routes. Only
          # list endpoints that ignore identity, keep the regexes anchored and
          # narrow, and keep this list in sync with the public (no
          # get_current_user) endpoints in the API. See api/README.md →
          # "Public endpoints and the production skip-auth footgun".
          # Each entry mirrors a GET endpoint that has no get_current_user
          # dependency in the API (see api/app/api/*.py). The optional `/?`
          # tolerates a trailing slash (FastAPI treats /x and /x/ as the same
          # route). KEEP THIS LIST IN SYNC with the API: adding/removing a
          # public GET there must be reflected here, and vice versa.
          skip_auth_routes = [
            # oauth2-proxy's own endpoints.
            "GET=^/oauth2/.*",

            # OpenAPI docs + schema (Swagger UI fetches openapi.json).
            "GET=^/api/docs/?$",
            "GET=^/api/redoc/?$",
            "GET=^/api/openapi.json$",

            # Product, template and plan reads.
            "GET=^/api/products/?$",
            "GET=^/api/products/[0-9]+/?$",
            "GET=^/api/products/[0-9]+/templates/?$",
            "GET=^/api/products/[0-9]+/templates/[0-9]+/?$",
            "GET=^/api/products/[0-9]+/icon/?$",
            "GET=^/api/products/[0-9]+/plans/?$",
            "GET=^/api/plans/[0-9]+/?$",
            "GET=^/api/plans/[0-9]+/templates/?$",

            # Hostname / domain helpers used by the deploy UI.
            "GET=^/api/hostnames/[^/]+/?$",
            "GET=^/api/domains/?$",
            "GET=^/api/cname-target/?$",

            # Static files (product icons, etc.).
            "GET=^/api/static/.*",
          ]
        EOT
      }
      extraArgs = {
        provider        = "keycloak-oidc"
        oidc-issuer-url = "${var.keycloak_url}/realms/${var.keycloak_realm}"
        redirect-url    = "https://${var.domain}/oauth2/callback"

        # REQUIRED, not an optimization. The freepod-prod/freepod-dev clients
        # set pkce_code_challenge_method = "S256" in tf/deps, which makes PKCE
        # *mandatory* at Keycloak. oauth2-proxy only sends a code challenge
        # when this flag is set; without it every authorization request is
        # rejected with
        #   error=invalid_request
        #   error_description=Missing parameter: code_challenge_method
        # and login fails for everyone. oauth2-proxy warns about this at
        # startup but still starts, so the pod goes Ready and the breakage
        # only shows up on the first real login.
        #
        # This flag and the client attribute are a matched pair: change one and
        # you must change the other.
        code-challenge-method = "S256"
        # cookie-domain     = ".dev.freepod.eu"
        # whitelist-domain  = ".dev.freepod.eu"
        pass-user-headers    = true
        set-xauthrequest     = true
        oidc-email-claim     = "email"
        reverse-proxy        = true
        skip-provider-button = true
        upstream             = "static://202"
        # skip_auth_routes now lives in configFile above (it needs multiple
        # entries; an extraArgs map can only express a single value).
        backend-logout-url = "${var.keycloak_url}/realms/${var.keycloak_realm}/protocol/openid-connect/logout?id_token_hint={id_token}"
      }
      service = {
        enabled    = true
        type       = "ClusterIP"
        portNumber = 8080
      }
      # The browser-facing /oauth2/* endpoints are served on the Caelus apex
      # host via the oauth2_proxy_route IngressRoute below (so the callback can
      # issue a host-only cookie). The chart's own login.${var.domain} ingress
      # is no longer used for cookie issuance.
      ingress = {
        enabled = false
      }
    })
  ]
}

resource "kubernetes_manifest" "oauth2_proxy_middleware" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "Middleware"
    metadata = {
      name      = "forward-auth"
      namespace = var.namespace
    }
    spec = {
      forwardAuth = {
        address = "http://oauth2-proxy.${var.namespace}.svc.cluster.local:8080/oauth2/auth"
        authResponseHeaders = [
          "X-Auth-Request-User",
          "X-Auth-Request-Email",
          "Authorization"
        ]
        trustForwardHeader = true
        authRequestHeaders = [
          "Cookie"
        ]
      }
    }
  }
}

# Serve all browser-facing /oauth2/* endpoints (start, callback, sign_out) on
# the Caelus apex host, routed straight to oauth2-proxy with NO forward-auth
# middleware so they are reachable unauthenticated. The callback issuing from
# this host is what makes the session cookie host-only on ${var.domain}.
# The explicit priority keeps this ahead of the catch-all `/` route on the
# caelus-ingress (which carries forward-auth), preventing an auth redirect loop.
resource "kubernetes_manifest" "oauth2_proxy_route" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "IngressRoute"
    metadata = {
      name      = "oauth2-endpoints"
      namespace = var.namespace
    }
    spec = {
      entryPoints = ["web", "websecure"]
      routes = [{
        match    = "Host(`${var.domain}`) && PathPrefix(`/oauth2`)"
        kind     = "Rule"
        priority = 100
        services = [{
          name = "oauth2-proxy"
          port = 8080
        }]
      }]
    }
  }
}

# NOTE: this errors-middleware (401 -> 302 redirect to Keycloak) is no longer
# attached to caelus-ingress. The landing page model relies on anonymous API
# requests returning a clean 401 that the SPA handles, with login initiated
# explicitly via /oauth2/start. The Middleware is kept defined here in case a
# future protected route wants edge-driven login redirects again.
resource "kubernetes_manifest" "oauth2_proxy_errors" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "Middleware"
    metadata = {
      name      = "oauth-errors"
      namespace = var.namespace
    }
    spec = {
      errors = {
        status = ["401"]
        query  = "/oauth2/start?rd=https://${var.domain}"
        statusRewrites = {
          "401" = "302"
        }
        service = {
          name = "oauth2-proxy"
          port = 8080
        }
      }
    }
  }
}
