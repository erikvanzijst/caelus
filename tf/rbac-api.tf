resource "kubernetes_service_account" "api" {
  metadata {
    name      = "caelus-api"
    namespace = local.namespace
  }
}

resource "kubernetes_cluster_role" "api" {
  metadata {
    name = local.rbac_name
  }

  rule {
    api_groups = ["*"]
    resources  = ["*"]
    verbs      = ["*"]
  }

  rule {
    non_resource_urls = ["*"]
    verbs             = ["*"]
  }
}

resource "kubernetes_cluster_role_binding" "api" {
  metadata {
    name = local.rbac_name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.api.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.api.metadata[0].name
    namespace = local.namespace
  }
}
