variable "haproxy_edge_ip" {
  description = "IP/CIDR of the homelab HAProxy edge, trusted for PROXY protocol on the web/websecure entrypoints."
  type        = string
}

variable "traefik_chart_version" {
  description = "Upstream Traefik Helm chart version. 39.0.5 ships Traefik app v3.6.10 — parity with the previously k3s-bundled Traefik."
  type        = string
  default     = "39.0.5"
}
