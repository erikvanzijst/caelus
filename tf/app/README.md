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

Namespace and domain are fixed per workspace in [`locals.tf`](./locals.tf):

- Dev namespace/domain: `caelus-dev` + `dev.freepod.eu`
- Prod namespace/domain: `caelus` + `freepod.eu`

The namespace's `environment` label defaults to `dev`/`prod` but can be
overridden with `-var environment=...`.

## Prerequisites

- Terraform `>= 1.0`
- Access to a Kubernetes cluster via `../../k8s/kubeconfigs/dev-k3s.yaml`
- Shared dependencies deployed (`../deps/`)

## Configuration

### Non-secret variables

Container images are workspace-derived in [`locals.tf`](./locals.tf): prod
tracks `:master`, dev tracks `:latest`. Override `api_image` / `ui_image` via
`-var` (or a `-var-file`) only to pin a specific tag, e.g. a SHA for rollback:

```bash
terraform apply -var 'api_image=ghcr.io/erikvanzijst/caelus/api:<sha>'
```

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

## SFTP entry point (sshpiper)

Each workspace deploys an sshpiperd instance (`sshpiper` module) that
terminates all tenant SFTP traffic for its environment and routes by SSH
username via `Pipe` CRs (CRD installed by `tf/deps/sshpiper`). klipper
ServiceLB binds the cluster-side port directly on the node.

Port chain (all internal hops avoid 22 — the hosts' own sshd lives there):

| Tier                      | prod            | dev                 |
|---------------------------|-----------------|---------------------|
| User-facing (home router) | `freepod.eu:22` | `dev.freepod.eu:23` |
| Homelab HAProxy           | `:2222`         | `:2223`             |
| Cluster node (this repo)  | `:2222`         | `:2223`             |

The HAProxy frontends live in the homelab repo
(github.com/erikvanzijst/homelab, OpenSpec change `sftp-haproxy-routes`);
the router port-forwards (`:22→2222`, `:23→2223`) are manual router
configuration. Override the cluster-side port with `-var sshpiper_port=<n>`.
