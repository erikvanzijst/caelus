# This amends the traefik helm chart that comes with and is managed by k3s.
# For it to work, we must first import the existing HelmChartConfig:
#
# terraform import 'module.system.kubernetes_manifest.traefik_config' 'apiVersion=helm.cattle.io/v1,kind=HelmChartConfig,namespace=kube-system,name=traefik'

resource "kubernetes_manifest" "traefik_config" {
  field_manager {
    force_conflicts = true
  }

  manifest = {
    apiVersion = "helm.cattle.io/v1"
    kind       = "HelmChartConfig"
    metadata = {
      name      = "traefik"
      namespace = "kube-system"
    }
    spec = {
      valuesContent = yamlencode({
        image = {
          tag = "3.6.10"
        }
        providers = {
          kubernetesIngress = {
            allowExternalNameServices = true
          }
          kubernetesIngressNginx = {
            enabled = true
          }
        }
        # Make `websecure` the only default entrypoint. A router (app Ingress)
        # that does not explicitly set `router.entrypoints` then binds :443 ONLY,
        # so its plain-HTTP :80 traffic falls through to the cluster-wide
        # HTTP->HTTPS redirect (redirect_https.tf) instead of being served plain.
        # This replaces the per-chart `router.entrypoints: websecure` annotation
        # we used to inject on every app — redirect routing is now a cluster
        # property, not a per-chart obligation. Routers that must serve :80 (the
        # redirect IngressRoute, the OAuth2 endpoints, the webhook receiver, and
        # cert-manager's HTTP-01 solver via its issuer ingressTemplate) declare
        # `web` explicitly and are unaffected.
        ports = {
          web = {
            asDefault = false
          }
          websecure = {
            asDefault = true
          }
        }
        # Preserve the source IP through klipper/servicelb. The homelab HAProxy edge
        # connects to this node's :443/:80 and sends PROXY protocol; with the default
        # externalTrafficPolicy=Cluster, kube-proxy SNATs the source to the node's CNI
        # gateway (10.42.0.1) BEFORE Traefik sees it, so proxyProtocol.trustedIPs never
        # matches and the real client IP is lost. `Local` keeps the edge IP as the TCP
        # source so the PROXY header is trusted and parsed.
        service = {
          spec = {
            externalTrafficPolicy = "Local"
          }
        }
        # Default certificate store: serve the *.freepod.eu wildcard (issued by
        # cert-manager via Cloudflare DNS-01, stored in kube-system) for any SNI
        # without a more specific cert. *.freepod.eu apps therefore need no per-app
        # TLS secret; custom-domain apps supply their own secret via cert-manager
        # (HTTP-01). See tf/deps/certmanager/.
        tlsStore = {
          default = {
            defaultCertificate = {
              secretName = "wildcard-freepod-eu-tls"
            }
          }
        }
        additionalArguments = [
          "--accesslog=true",
          # The homelab HAProxy edge now passes through raw TLS (we terminate it
          # here) and conveys the real client IP via PROXY protocol. Trust it ONLY
          # from the edge IP and surface the client IP as X-Forwarded-For. We no
          # longer blanket-trust forwarded headers (forwardedheaders.insecure) — that
          # would let any LAN peer spoof them now that TLS terminates on this side.
          "--entrypoints.web.proxyProtocol.trustedIPs=${var.haproxy_edge_ip}",
          "--entrypoints.websecure.proxyProtocol.trustedIPs=${var.haproxy_edge_ip}",
          # NOTE: deliberately NO `--entrypoints.web.http.redirections.*` here. That
          # is an ENTRYPOINT-LEVEL redirect applied before router matching, so it
          # shadows cert-manager's HTTP-01 solver Ingress and deadlocks issuance for
          # custom domains (and leaks the internal :8443 port). The HTTP->HTTPS
          # redirect is instead a low-priority web-only IngressRoute + redirectScheme
          # Middleware (redirect_https.tf) that the solver's longer rule out-ranks;
          # apps reach it because `websecure` is the default entrypoint (see `ports`
          # above), so their :80 traffic is not served by the app itself.
        ]
      })
    }
  }
}
