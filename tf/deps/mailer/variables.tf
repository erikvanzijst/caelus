variable "namespace" {
  description = "Namespace to deploy into"
  type = string
}

variable "smtp_host" {
  description = "SMTP server (e.g. smtp.example.com)"
  type        = string
}

variable "smtp_port" {
  description = "SMTP server port"
  type        = string
}

variable "smtp_username" {
  description = "SMTP username"
  type        = string
}

variable "smtp_password" {
  description = "SMTP password"
  type        = string
  sensitive   = true
}
