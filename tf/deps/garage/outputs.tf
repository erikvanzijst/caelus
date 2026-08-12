# Read the generated credentials back out of the cluster.
#
# Terraform cannot pre-generate these: Garage mints the key material itself and
# `ImportKey` rejects keys it did not generate. So the Job creates them, writes
# them to a Secret, and this data source reads them back — the same shape as the
# Keycloak client secrets, which also only exist after an apply.
data "kubernetes_secret" "garage_keys" {
  metadata {
    name      = local.keys_secret_name
    namespace = var.namespace
  }

  # The Secret does not exist until the Job has run. `wait_for_completion` on
  # the Job means this is read after provisioning succeeded, not during.
  depends_on = [kubernetes_job.provision]
}

# `nonsensitive()` because an access key ID is an identifier, not a credential.
# The whole `data` map of a kubernetes_secret data source is sensitive-marked,
# and that marking propagates to anything derived from it — so without this,
# every consumer would have to declare the key ID sensitive too, and
# `terraform output` / `terraform plan` would show `(sensitive value)` where the
# operator most needs to read it: confirming that each environment got its own
# key. The ID is not secret by any measure — it travels in the clear in the
# `X-Amz-Credential` parameter of every presigned URL this store hands out.
#
# The secret access key below keeps its marking, which is the half that matters.
output "access_key_ids" {
  description = "S3 access key ID per environment. Not a credential on its own."
  value       = { for env in var.environments : env => nonsensitive(data.kubernetes_secret.garage_keys.data["${env}_access_key_id"]) }
}

output "secret_access_keys" {
  description = "S3 secret access key per environment."
  value       = { for env in var.environments : env => data.kubernetes_secret.garage_keys.data["${env}_secret_access_key"] }
  sensitive   = true
}

# The bucket name IS the environment name — single-sourced from the same
# variable the provisioning script derives its names from, so tf/app cannot
# drift from what was actually created.
output "buckets" {
  description = "S3 bucket name per environment."
  value       = { for env in var.environments : env => env }
}

output "s3_endpoint" {
  description = "Public S3 endpoint URL, for the Caelus API's S3 client."
  value       = "https://blob.${var.domain}"
}

output "s3_region" {
  description = "SigV4 signing region. Must match on both sides."
  value       = local.s3_region
}
