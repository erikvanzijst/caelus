variable "namespace" {
  description = "Namespace for the sshpiperd deployment (workspace-scoped)"
  type        = string
}

variable "ssh_port" {
  description = "Cluster-side SSH port bound on the node via klipper ServiceLB (2222 prod, 2223 dev)"
  type        = number
}

variable "sshpiper_image" {
  description = "sshpiperd image; keep the tag in sync with the Pipe CRD vendored in tf/deps/sshpiper"
  type        = string
  default     = "farmer1992/sshpiperd:v1.5.4"
}

variable "rbac_name" {
  description = "Name for the cluster-scoped RBAC objects (must be unique per environment)"
  type        = string
}
