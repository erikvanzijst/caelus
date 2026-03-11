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
        additionalArguments = [
          "--accesslog=true",
          # Trust X-Forwarded-* headers from any source on both the web (HTTP) and websecure (HTTPS) entrypoints.
          # Needed because we're behind a reverse proxy (our homelab) that injects those headers:
          "--entrypoints.web.forwardedheaders.insecure=true",
          "--entrypoints.websecure.forwardedheaders.insecure=true",
        ]
      })
    }
  }
}
