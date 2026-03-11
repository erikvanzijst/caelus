resource "kubernetes_persistent_volume_claim" "postgres_pvc" {
  metadata {
    name      = "postgres-pvc"
    namespace = var.namespace
  }

  wait_until_bound = false

  spec {
    access_modes = ["ReadWriteOnce"]
    resources {
      requests = {
        storage = "1Gi"
      }
    }
  }
}

