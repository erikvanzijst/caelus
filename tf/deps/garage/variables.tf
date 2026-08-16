variable "namespace" {
  description = "Namespace to deploy into"
  type        = string
}

variable "domain" {
  description = "The base domain name (e.g. freepod.eu). The S3 endpoint is published at blob.<domain>."
  type        = string
}

variable "garage_image" {
  description = "Garage container image, pinned to an explicit version."
  type        = string
  default     = "dxflrs/garage:v2.3.0"
}

variable "kubectl_image" {
  description = "Image for the provisioning Job. Must provide curl, jq and kubectl."
  type        = string
  default     = "alpine/k8s:1.31.1"
}

variable "meta_pvc_size" {
  description = "Size of the Garage metadata PVC (LMDB). Small, but must not be starved."
  type        = string
  default     = "2Gi"
}

variable "data_pvc_size" {
  description = "Size of the Garage object-data PVC. This is the hard ceiling on this dependency's contribution to node disk pressure."
  type        = string
  default     = "20Gi"
}

variable "cpu_request" {
  description = "CPU request. Idle Garage is cheap; do not over-reserve on a full node."
  type        = string
  default     = "100m"
}

variable "cpu_limit" {
  description = "CPU limit."
  type        = string
  default     = "1"
}

variable "memory_request" {
  description = "Memory request."
  type        = string
  default     = "256Mi"
}

variable "memory_limit" {
  description = "Memory limit. Caps a multipart-upload burst."
  type        = string
  default     = "1Gi"
}

# --- Provisioning ----------------------------------------------------------

variable "environments" {
  description = "Environments to provision a bucket and access key for. The bucket is named for the environment alone; the key is `caelus-api-<env>`. Single source of the naming convention — do not hardcode these names elsewhere."
  type        = list(string)
  default     = ["dev", "prod"]
}

variable "object_expiry_days" {
  description = "Age in days after which objects (and abandoned multipart uploads) are expired by the bucket lifecycle rules. Objects here are write-once/read-once and worthless within ~24h; 2 days leaves slack."
  type        = number
  default     = 2
}

# --- Secrets ---------------------------------------------------------------

variable "admin_token" {
  description = "Garage admin API master token."
  type        = string
  sensitive   = true
}

variable "rpc_secret" {
  description = "Garage inter-node RPC secret, 32 bytes hex (`openssl rand -hex 32`)."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9a-fA-F]{64}$", var.rpc_secret))
    error_message = "rpc_secret must be exactly 32 bytes of hex (64 hex characters). Generate one with `openssl rand -hex 32`."
  }
}
