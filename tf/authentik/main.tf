resource "helm_release" "authentik" {
  name       = "authentik"
  namespace  = var.namespace
  chart      = "authentik/authentik"
  version    = "2026.2.1"

  create_namespace = false

  values = [
    yamlencode({
      authentik = {
        secret_key = "AMPBRycrJBSmEDRPeriqR9w0cSAapYv9gsbku51rZBUGX1wEQb"
        error_reporting = {
          enabled = false
        }
        postgresql = {
          password = "VSlj56nlxdp3dMXJZm2QIM"
        }
        email = {
          host = "smtp.purelymail.com"
          port = 465
          use_ssl = true
          use_tls = false
          username = var.smtp_username
          password = var.smtp_password
          from = "caelus@deprutser.be"
        }
      }

      server = {
        ingress = {
          ingressClassName = "traefik"
          enabled = true
          hosts = ["authentik.app.deprutser.be"]
        }
      }

      postgresql = {
        enabled = true
        auth = {
          password = "VSlj56nlxdp3dMXJZm2QIM"
        }
      }
    })
  ]
}
