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
          # custom domains (and leaks the internal :8443 port). HTTP->HTTPS redirect
          # is a follow-up (a low-priority web-only IngressRoute + redirectScheme
          # Middleware that the solver's longer rule out-ranks); apps stay reachable
          # on plain HTTP until then.
        ]
      })
    }
  }
}
