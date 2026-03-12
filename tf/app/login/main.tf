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
        clientID     = "caelus-dev"
        clientSecret = var.oauth2_proxy_client_secret
        cookieSecret = var.oauth2_proxy_cookie_secret
        configFile   = <<-EOT
          email_domains = ["*"]
          upstreams = ["file:///dev/null"]
          cookie_secure = false
          cookie_domains = ["${var.domain}"]
          whitelist_domains = ["${var.domain}"]
          provider = "keycloak-oidc"
        EOT
      }
      extraArgs = {
        provider             = "keycloak-oidc"
        oidc-issuer-url      = "https://keycloak.app.deprutser.be/realms/master"
        redirect-url         = "https://login.${var.domain}/oauth2/callback"
        # cookie-domain     = ".dev.deprutser.be"
        # whitelist-domain  = ".dev.deprutser.be"
        pass-user-headers    = true
        set-xauthrequest     = true
        oidc-email-claim     = "email"
        reverse-proxy        = true
        skip-provider-button = true
        upstream             = "static://202"
        skip-auth-route      = "GET=^/oauth2/.*"
        backend-logout-url   = "https://keycloak.app.deprutser.be/realms/master/protocol/openid-connect/logout?id_token_hint={id_token}"
      }
      service = {
        enabled    = true
        type       = "ClusterIP"
        portNumber = 8080
      }
      ingress = {
        enabled          = true
        ingressClassName = "traefik"
        pathType         = "Prefix"
        hosts = ["login.${var.domain}"]
        paths = ["/oauth2"]
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

resource "kubernetes_manifest" "oauth2_signout_route" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "IngressRoute"
    metadata = {
      name      = "oauth2-signout"
      namespace = var.namespace
    }
    spec = {
      entryPoints = ["web", "websecure"]
      routes = [{
        match    = "Host(`${var.domain}`) && PathPrefix(`/oauth2/sign_out`)"
        kind     = "Rule"
        services = [{
          name = "oauth2-proxy"
          port = 8080
        }]
      }]
    }
  }
}

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
