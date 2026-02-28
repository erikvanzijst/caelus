resource "kubernetes_persistent_volume_claim" "postgres_pvc" {
  metadata {
    name      = "caelus-db-pvc"
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

resource "kubernetes_persistent_volume_claim" "sqlite_pvc" {
  metadata {
    name      = "caelus-sqlite-pvc"
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
