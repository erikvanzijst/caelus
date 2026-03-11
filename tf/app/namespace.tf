resource "kubernetes_namespace" "caelus" {
  metadata {
    name = local.ns_caelus

    labels = {
      name        = local.ns_caelus
      environment = local.environment
    }
  }
}

resource "kubernetes_namespace" "login" {
  metadata {
    name = local.is_prod_workspace ? "login" : "login-dev"
  }
}
