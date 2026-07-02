# Freepod's ingress controller is a self-managed Traefik Helm release (./helm/traefik).
module "traefik" {
  source          = "./helm/traefik"
  haproxy_edge_ip = var.haproxy_edge_ip
}
