# The build worker: claims queued builds, creates a Kubernetes Job per build in
# the builds namespace, mirrors each Job's output into the database, and adopts
# its outcome.
#
# It runs in the *platform* namespace, not the builds namespace. It is trusted
# platform code holding database credentials and Kubernetes permissions; the
# only thing that belongs in the builds namespace is the untrusted build pod it
# creates there.
resource "kubernetes_deployment" "build_worker" {
  metadata {
    name      = "caelus-build-worker"
    namespace = var.namespace
    labels = {
      app = "caelus-build-worker"
    }
  }

  spec {
    # Concurrency is `CAELUS_BUILD_MAX_IN_FLIGHT`, not this number. One worker
    # advances every running build on each pass without blocking on any of
    # them, so more replicas would buy nothing but contention — which is
    # exactly why the in-flight limit is a setting rather than a replica count.
    replicas = 1

    selector {
      match_labels = {
        app = "caelus-build-worker"
      }
    }

    # Recreate, unlike the reconcile worker's RollingUpdate. A rolling update
    # briefly runs two workers, and two workers can each observe "nothing
    # running" and each claim a build, momentarily exceeding the in-flight
    # limit on a node that has no headroom for it. The cost is a few seconds
    # with no worker, which is invisible: builds are advanced by the next pass.
    strategy {
      type = "Recreate"
    }

    template {
      metadata {
        labels = {
          app = "caelus-build-worker"
        }
      }

      spec {
        # The API's ServiceAccount, which already holds the cluster permissions
        # needed to create, read and delete Jobs and to read pod logs in the
        # builds namespace. Reused rather than given its own so there is one
        # platform identity to reason about.
        service_account_name = kubernetes_service_account.api.metadata[0].name

        # Deliberately no `alembic upgrade head` init container, unlike
        # deployment-api.tf and worker.tf. Two components already race to apply
        # migrations behind an advisory lock; adding a third contender buys
        # nothing, and this worker cannot be the first thing deployed anyway.
        container {
          image             = var.api_image
          image_pull_policy = "Always"
          name              = "build-worker"
          command           = ["caelus", "build-worker"]

          env_from {
            config_map_ref {
              name = "caelus-api-config"
            }
          }

          env_from {
            secret_ref {
              name = "caelus-db"
            }
          }

          # The object store credential: the worker mints the presigned GET
          # that the build pod uses to fetch its artifact. The build pod itself
          # never sees these — it receives only the resulting expiring URL.
          env_from {
            secret_ref {
              name = kubernetes_secret.s3.metadata[0].name
            }
          }
        }
      }
    }
  }

  # `kubectl rollout restart` — which is all ./scripts/rollout.sh does — forces
  # a new pod by stamping this annotation onto the pod template. It is an
  # operational fact ("someone restarted this at 15:19"), not desired state, so
  # Terraform must not try to remove it: doing so shows up as permanent drift
  # after every rollout and rolls the deployment again on the next apply.
  #
  # Scoped to the single key rather than the whole annotations map, so an
  # annotation genuinely managed here would still surface as drift.
  lifecycle {
    ignore_changes = [
      spec[0].template[0].metadata[0].annotations["kubectl.kubernetes.io/restartedAt"],
    ]
  }

  depends_on = [kubernetes_cluster_role_binding.api]
}
