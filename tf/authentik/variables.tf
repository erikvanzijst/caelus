variable "namespace" {
  description = "Namespace to deploy into"
  type = string
}

variable "smtp_password" {
  description = "SMTP password for outbound email (use secrets.auto.tfvars)"
  type        = string
  sensitive   = true
}

variable "smtp_username" {
  description = "SMTP username for outbound email"
  type        = string
  default     = "caelus@deprutser.be"
}
