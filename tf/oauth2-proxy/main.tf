# https://junwu.shouyicheng.com/posts/keycloak-oauth2-proxy-secure-web-application/
#
# helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests
# helm repo update

resource "helm_release" "oauth2_proxy" {
  name = "oauth2-proxy"
  chart            = "oauth2-proxy/oauth2-proxy"
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
          cookie_domains = ["app.deprutser.be", "dev.deprutser.be"]
          whitelist_domains = ["app.deprutser.be", "dev.deprutser.be"]
          provider = "keycloak-oidc"
        EOT
      }
      extraArgs = {
        provider             = "keycloak-oidc"
        oidc-issuer-url      = "https://keycloak.${var.domain}/realms/master"
        redirect-url         = "https://login.dev.deprutser.be/oauth2/callback"
        # cookie-domain     = ".dev.deprutser.be"
        # whitelist-domain  = ".dev.deprutser.be"
        pass-user-headers    = true
        set-xauthrequest     = true
        reverse-proxy        = true
        skip-provider-button = true
        upstream             = "static://202"
        skip-auth-route      = "GET=^/oauth2/.*"
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
        hosts = ["login.dev.deprutser.be"]
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
        query  = "/oauth2/start?rd={url}"
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
