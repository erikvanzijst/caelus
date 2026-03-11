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
