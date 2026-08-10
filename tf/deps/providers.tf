terraform {
  required_version = ">= 1.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    # keycloak/keycloak is the maintained continuation of mrparkers/keycloak,
    # which has had no release since January 2024. Do not switch back.
    #
    # Capped below 5.8.0 on purpose. From 5.8.0 the provider unconditionally
    # sends `bruteForceStrategy` in the realm representation, a field added in
    # Keycloak 26. Keycloak 24.0.5 (what we run — see keycloak/Dockerfile)
    # rejects the whole request with
    #   400 {"errorMessage":"unable to read contents from stream"}
    # so realm creation fails outright. Verified by bisecting the request body:
    # removing that one field turns the 400 into a 201. Raise this cap only
    # together with a Keycloak upgrade to 26.x.
    keycloak = {
      source  = "keycloak/keycloak"
      version = "~> 5.7.0"
    }
  }
}

provider "kubernetes" {
  config_path = "../../k8s/kubeconfigs/dev-k3s.yaml"
}

provider "helm" {
  kubernetes {
    config_path = "../../k8s/kubeconfigs/dev-k3s.yaml"
  }
}

# Authenticates as the bootstrap instance administrator, which lives in the
# `master` realm (the provider's default login realm). It manages realm,
# client, client-scope and group configuration only — never end-user accounts.
provider "keycloak" {
  client_id = "admin-cli"
  username  = "admin"
  password  = var.keycloak_admin_password
  url       = var.keycloak_url
}
