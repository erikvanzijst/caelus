variable "haproxy_edge_ip" {
  description = "IP/CIDR of the homelab HAProxy edge, trusted for PROXY protocol on the web/websecure entrypoints."
  type        = string
}
