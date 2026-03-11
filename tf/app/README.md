# Caelus App Deployment

This Terraform project deploys the Caelus application (API, UI, worker,
OAuth2-proxy, and Postgres) into a Kubernetes cluster.

Shared dependencies (Keycloak, Echo) are managed separately in `../deps/`.

## What It Creates

- Namespaces: `caelus` / `caelus-dev`, `login` / `login-dev`
- API deployment + service
- UI deployment + service
- Worker deployment (`caelus worker --follow`)
- Postgres deployment + service
- PVCs for Postgres and SQLite data
- ConfigMap + Secret for API/DB configuration
- ServiceAccount + ClusterRole + ClusterRoleBinding for API/worker
- Ingress (`caelus-ingress`) for `/` and `/api`
- OAuth2-proxy (Helm chart) + Traefik middleware

## Environment Model (Dev vs Prod)

This project uses Terraform workspaces for environment separation.

- `default` workspace: **dev** (safe default on fresh clone)
- `prod` workspace: **prod**

Workspace defaults:

- Dev namespace/domain: `caelus-dev` + `dev.deprutser.be`
- Prod namespace/domain: `caelus` + `app.deprutser.be`

These defaults can still be overridden with variables (`namespace`, `domain`)
or `-var-file`.

## Prerequisites

- Terraform `>= 1.0`
- Access to a Kubernetes cluster via `../../k8s/kubeconfigs/dev-k3s.yaml`
- Shared dependencies deployed (`../deps/`)

## Configuration

### Non-secret variables

Set in [`terraform.tfvars`](./terraform.tfvars):

- `api_image`
- `ui_image`

### Environment var files (optional)

- [`prod.tfvars`](./prod.tfvars)

### Secret variables

Create `secrets.auto.tfvars` (gitignored):

```hcl
db_password                = "replace-with-a-strong-password"
smtp_password              = "replace-with-smtp-password"
oauth2_proxy_client_secret = "replace-with-oauth2-client-secret"
oauth2_proxy_cookie_secret = "replace-with-oauth2-cookie-secret"
```

## Deploy

### Dev (default)

```bash
cd tf/app
terraform init
terraform apply
```

### Prod

```bash
cd tf/app
terraform init
terraform workspace select prod || terraform workspace new prod
terraform apply
```

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

- Cluster-scoped RBAC names include the namespace (e.g.
  `caelus-api-caelus-dev` vs `caelus-api-caelus`) so dev/prod can coexist.
- State is local by default. Use a remote backend for shared/team usage.
