# https://junwu.shouyicheng.com/posts/keycloak-oauth2-proxy-secure-web-application/
#
# helm repo add oauth2-proxy https://oauth2-proxy.github.io/manifests
# helm repo update

resource "helm_release" "oauth2_proxy" {
  name       = "oauth2-proxy"
  # repository = "https://oauth2-proxy.github.io/manifests"
  chart      = "oauth2-proxy/oauth2-proxy"
  version    = "10.1.4"
  namespace  = var.namespace
  create_namespace = false

  values = [
    yamlencode({
      replicaCount = 1
      config = {
        # https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/keycloak_oidc
        provider      = "keycloak-oidc"
        clientID      = "caelus-dev"
        clientSecret  = var.oauth2_proxy_client_secret
        cookieSecret  = var.oauth2_proxy_cookie_secret
        redirectUrl   = "https://login.${var.domain}/oauth2/callback"
        oidcIssuerUrl = "https://keycloak.${var.domain}/realms/master"
        # providerDisplayName = "Keycloak"
        emailDomains       = ["*"]
        whitelistDomains   = [".app.deprutser.be", ".dev.deprutser.be"]
        setXAuthRequest    = true
        cookieName         = "_oauth2_proxy"
        cookieSecure       = true
        sessionStoreType   = "cookie"
        skipProviderButton = true
        # proxyPrefix         = "/oauth2"
      }
      extraArgs = {
        provider          = "keycloak-oidc"
        oidc-issuer-url = "https://keycloak.${var.domain}/realms/master"
        # cookie-domain     = ".app.deprutser.be"
        # whitelist-domain  = "*.app.deprutser.be"
        pass-user-headers = true
        set-xauthrequest  = true
        # http-address = "0.0.0.0:8080"
        upstream     = "static://202"
      }
      service = {
        enabled    = true
        type       = "ClusterIP"
        portNumber = 8080
      }
      ingress = {
        enabled          = true
        ingressClassName = "traefik"
        hosts            = ["login.${var.domain}"]
        paths            = ["/oauth2"]
        annotations = {
          "traefik.ingress.kubernetes.io/rule-type" = "path-only"
        }
      }
      # resources = {
      #   requests = {
      #     memory = "128Mi"
      #     cpu    = "100m"
      #   }
      #   limits = {
      #     memory = "256Mi"
      #     cpu    = "200m"
      #   }
      # }
      # readinessProbe = {
      #   path = "/oauth2/healthz"
      # }
      # livenessProbe = {
      #   path = "/oauth2/healthz"
      # }
    })
  ]
}

resource "kubernetes_manifest" "oauth2_proxy_middleware" {
  manifest = {
    apiVersion = "traefik.io/v1alpha1"
    kind       = "Middleware"
    metadata = {
      name      = "oauth2-proxy-forward-auth"
      namespace = var.namespace
    }
    spec = {
      forwardAuth = {
        address = "http://oauth2-proxy.${var.namespace}.svc.cluster.local/oauth2/auth"
        authResponseHeaders = [
          "X-Auth-Request-User",
          "X-Auth-Request-Email",
          "Authorization"
        ]
        trustForwardHeader = true
      }
    }
  }
}
