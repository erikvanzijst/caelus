# Terraform Deployment

This directory contains the Terraform project that deploys Caelus itself
(API, UI, worker, Postgres, and ingress) into a Kubernetes cluster.

## What It Creates

Terraform manages these Kubernetes resources:

- Namespace
- API deployment + service
- UI deployment + service
- Worker deployment (`caelus worker --follow`)
- Postgres deployment + service
- PVCs for Postgres and SQLite data
- ConfigMap + Secret for API/DB configuration
- ServiceAccount + ClusterRole + ClusterRoleBinding for API/worker
- Ingress (`caelus-ingress`) for `/` and `/api`

## Environment Model (Dev vs Prod)

This project uses Terraform workspaces for environment separation.

- `default` workspace: **dev** (safe default on fresh clone)
- `prod` workspace: **prod**

Workspace defaults:

- Dev namespace/domain: `caelus-dev` + `dev.deprutser.be`
- Prod namespace/domain: `caelus` + `app.deprutser.be`

These defaults can still be overridden with variables (`namespace`, `domain`) or
`-var-file`.

## Prerequisites

- Terraform `>= 1.0`
- Access to a Kubernetes cluster
- A kubeconfig file available at:
  - `../k8s/kubeconfigs/dev-k3s.yaml`

Provider config is in [`providers.tf`](./providers.tf):

```hcl
provider "kubernetes" {
  config_path = "../k8s/kubeconfigs/dev-k3s.yaml"
}
```

## Configuration

### Shared non-secret variables

Set in [`terraform.tfvars`](./terraform.tfvars):

- `api_image`
- `ui_image`

### Environment var files (optional)

- [`prod.tfvars`](./prod.tfvars)

This is useful for explicit prod runs.

### Secret variables

`db_password` is required and has no default.

Create `tf/secrets.auto.tfvars`:

```hcl
db_password = "replace-with-a-strong-password"
```

`secrets.auto.tfvars` is gitignored.

## Deploy

### Fresh clone default (dev)

```bash
cd tf
terraform init
terraform apply
```

This deploys to `caelus-dev` with ingress host `dev.deprutser.be`.

### Explicit prod deployment

```bash
cd tf
terraform init
terraform workspace select prod || terraform workspace new prod
terraform apply
```

`-var-file=prod.tfvars` is optional and only needed if you add explicit
prod-only overrides beyond workspace defaults.

## Verify

```bash
terraform workspace show
terraform output
kubectl get ns caelus-dev caelus
kubectl -n <namespace> get pods,svc,pvc,ingress
```

## Teardown

Destroy only the currently selected workspace environment:

```bash
terraform destroy
```

## Notes

- Cluster-scoped RBAC names are namespace-scoped in naming (for example
  `caelus-api-caelus-dev` vs `caelus-api-caelus`) so dev/prod can coexist in
  one cluster.
- `api_replicas` and `ui_replicas` variables exist but deployments are currently
  hardcoded to `replicas = 1`.
- State is local by default. Use a remote backend for shared/team usage.
