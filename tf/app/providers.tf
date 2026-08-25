terraform {
  required_version = ">= 1.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    # Generates the tenant cluster's three passwords (tf/app/caelus/tenant-db.tf).
    # They live only in Terraform state, which is gitignored -- restoring an
    # environment from a lost state file means resetting them by hand against
    # the surviving PGDATA.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
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
