# Bucket, access-key and lifecycle provisioning (design D2).
#
# Garage has no IAM, so there is no S3-policy-shaped Terraform resource to use,
# and `ImportKey` rejects keys Garage did not generate — so the tidy pattern of
# "Terraform generates the credential, tells Garage, writes the Secret from
# state" is unavailable. Garage must mint the key and something must read it
# back. That something is this Job.
#
# Re-running it on every apply is deliberate: it makes provisioning declarative
# in effect even though Garage offers no declarative surface, and it repairs
# hand-made drift. Every step in the script reads before it writes, so a re-run
# never rotates an existing key.

locals {
  keys_secret_name = "garage-keys"
  creds_dir        = "/creds"

  provision_script = file("${path.module}/scripts/provision.sh")
  lifecycle_script = file("${path.module}/scripts/lifecycle.sh")

  # Job specs are immutable, so the Job is named after a digest of everything
  # that determines what it does. Change a script, the environment list or the
  # expiry, and Terraform replaces the Job — which is what "re-run when the
  # script ConfigMap changes" means in practice.
  provision_hash = substr(sha256(join("\n", [
    local.provision_script,
    local.lifecycle_script,
    join(",", var.environments),
    tostring(var.object_expiry_days),
    var.kubectl_image,
    var.aws_cli_image,
  ])), 0, 10)

  environments_arg = join(" ", var.environments)
}

resource "kubernetes_service_account" "provisioner" {
  metadata {
    name      = "garage-provisioner"
    namespace = var.namespace
  }
}

# Scoped to writing one Secret in this one namespace. No cross-namespace
# permission: the Job must not write into tf/app's namespaces, which would
# invert the ownership boundary between the two root modules (design D2).
resource "kubernetes_role" "provisioner" {
  metadata {
    name      = "garage-provisioner"
    namespace = var.namespace
  }

  # `create` cannot be constrained by resourceNames — at authorization time the
  # object does not exist yet, so Kubernetes ignores resourceNames on create and
  # a rule carrying them would simply never authorize it. Hence two rules: an
  # unnamed create, and everything else pinned to the one Secret.
  rule {
    api_groups = [""]
    resources  = ["secrets"]
    verbs      = ["create"]
  }

  rule {
    api_groups     = [""]
    resources      = ["secrets"]
    resource_names = [local.keys_secret_name]
    # `kubectl apply` reads, then PATCHes; `update` covers the non-apply path.
    verbs = ["get", "update", "patch"]
  }
}

resource "kubernetes_role_binding" "provisioner" {
  metadata {
    name      = "garage-provisioner"
    namespace = var.namespace
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role.provisioner.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.provisioner.metadata[0].name
    namespace = var.namespace
  }
}

resource "kubernetes_config_map" "provisioner_scripts" {
  metadata {
    name      = "garage-provisioner-scripts"
    namespace = var.namespace
  }

  data = {
    "provision.sh" = local.provision_script
    "lifecycle.sh" = local.lifecycle_script
  }
}

resource "kubernetes_job" "provision" {
  metadata {
    name      = "garage-provision-${local.provision_hash}"
    namespace = var.namespace
  }

  spec {
    backoff_limit = 3

    template {
      metadata {
        labels = { app = "garage-provisioner" }
      }

      spec {
        service_account_name = kubernetes_service_account.provisioner.metadata[0].name
        restart_policy       = "Never"

        # Step one: buckets, access keys and permission grants, over the Garage
        # admin API. See the header of scripts/provision.sh for why this cannot
        # run in the Garage image (FROM scratch, no shell) and why the CLI is
        # not usable from a second pod (RPC needs the node ID).
        init_container {
          name    = "provision"
          image   = var.kubectl_image
          command = ["/bin/sh", "/scripts/provision.sh"]

          env {
            name = "GARAGE_ADMIN_URL"
            # The headless Service, which publishes not-ready addresses: on a
            # fresh install Garage is deliberately unready until its layout is
            # committed, and this step exists precisely to say so.
            value = "http://${kubernetes_service.garage.metadata[0].name}.${var.namespace}.svc.cluster.local:3903"
          }

          env {
            name = "GARAGE_ADMIN_TOKEN"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.garage.metadata[0].name
                key  = "admin_token"
              }
            }
          }

          env {
            name  = "ENVIRONMENTS"
            value = local.environments_arg
          }

          env {
            name  = "KEYS_SECRET_NAME"
            value = local.keys_secret_name
          }

          env {
            name  = "NAMESPACE"
            value = var.namespace
          }

          env {
            name  = "CREDS_DIR"
            value = local.creds_dir
          }

          # Long enough that an operator can complete the one-time layout
          # bootstrap in another terminal while the apply waits, short enough
          # that an unattended apply fails with a useful message rather than
          # hanging indefinitely.
          env {
            name  = "HEALTH_TIMEOUT_SECONDS"
            value = "600"
          }

          volume_mount {
            name       = "scripts"
            mount_path = "/scripts"
            read_only  = true
          }

          volume_mount {
            name       = "creds"
            mount_path = local.creds_dir
          }
        }

        # Step two: the bucket lifecycle rules. Separate from step one because
        # lifecycle is an S3-API call (PutBucketLifecycleConfiguration), not an
        # admin-API or `garage` CLI one, so it needs an S3 client and the
        # bucket's own access key rather than an admin token.
        container {
          name    = "lifecycle"
          image   = var.aws_cli_image
          command = ["/bin/sh", "/scripts/lifecycle.sh"]

          env {
            name  = "S3_ENDPOINT"
            value = "http://${kubernetes_service.garage_s3.metadata[0].name}.${var.namespace}.svc.cluster.local:3900"
          }

          env {
            name  = "AWS_DEFAULT_REGION"
            value = local.s3_region
          }

          env {
            name  = "ENVIRONMENTS"
            value = local.environments_arg
          }

          env {
            name  = "OBJECT_EXPIRY_DAYS"
            value = tostring(var.object_expiry_days)
          }

          env {
            name  = "CREDS_DIR"
            value = local.creds_dir
          }

          volume_mount {
            name       = "scripts"
            mount_path = "/scripts"
            read_only  = true
          }

          volume_mount {
            name       = "creds"
            mount_path = local.creds_dir
          }
        }

        volume {
          name = "scripts"
          config_map {
            name         = kubernetes_config_map.provisioner_scripts.metadata[0].name
            default_mode = "0555"
          }
        }

        # Memory-backed: the access keys pass from step one to step two through
        # this volume and never touch the node's disk.
        volume {
          name = "creds"
          empty_dir {
            medium = "Memory"
          }
        }
      }
    }
  }

  # Terraform blocks the apply until provisioning has actually succeeded, so
  # the data source below reads a Secret that exists. The generous timeout is
  # the health wait in step one (see HEALTH_TIMEOUT_SECONDS).
  wait_for_completion = true

  timeouts {
    create = "20m"
    update = "20m"
  }

  depends_on = [
    kubernetes_stateful_set.garage,
    kubernetes_role_binding.provisioner,
  ]
}
