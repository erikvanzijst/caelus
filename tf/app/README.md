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

Note that the API image also carries the product catalog (`products/catalog/`),
which two init containers apply in order before the API starts: `migrate`
(`alembic upgrade head`) then `catalog` (`caelus catalog apply`). Pinning
`api_image` therefore pins the catalog as well, and rolling back to an older SHA
rolls the catalog back with it. A malformed catalog fails the `catalog` init
container, so the pod never becomes ready and the previous ReplicaSet keeps
serving.

### Secret variables

Create `secrets.auto.tfvars` (gitignored):

```hcl
db_password   = "replace-with-a-strong-password"
smtp_password = "replace-with-smtp-password"

oauth2_proxy_client_ids = {
  default = "freepod-dev"
  prod    = "freepod-prod"
}

# Read these from tf/deps, which owns the clients:
#   terraform -chdir=../deps output -raw freepod_dev_client_secret
#   terraform -chdir=../deps output -raw freepod_prod_client_secret
oauth2_proxy_client_secrets = {
  default = "replace-with-freepod-dev-client-secret"
  prod    = "replace-with-freepod-prod-client-secret"
}

oauth2_proxy_cookie_secret = "replace-with-oauth2-cookie-secret"
```

### Authentication

oauth2-proxy authenticates against the **`freepod` realm** (not `master`),
using the per-environment client selected above. The clients themselves are
declared in `tf/deps/keycloak-config/`; this root module only *selects* which
one the current workspace uses. It declares no Keycloak resources.

The non-prod workspace additionally sets `allowed_groups = ["freepod-dev"]`
on oauth2-proxy, so `dev.freepod.eu` is restricted to members of that Keycloak
group. Prod sets no group restriction. Membership is administered in Keycloak
and needs no apply here.

Both clients require PKCE `S256`, so oauth2-proxy runs with
`--code-challenge-method=S256`. **These are a matched pair.** Remove one and
every login fails with `invalid_request: Missing parameter:
code_challenge_method` — and oauth2-proxy will still start and pass its
readiness probe, so the pod looks healthy while authentication is broken.

**Apply `tf/deps` first.** oauth2-proxy resolves OIDC discovery at startup and
fails its readiness probe if the realm or clients are missing, so this module
must never be applied against a realm that does not yet exist.

### Bearer tokens for external API clients

oauth2-proxy also accepts a verified JWT bearer token in place of its session
cookie (`--skip-jwt-bearer-tokens`), so non-browser clients can authenticate
with a Keycloak access token. Three settings make this work, and they are
interdependent:

1. `--skip-jwt-bearer-tokens=true` — verify the token and build a session from
   its claims, after which `--set-xauthrequest` emits `X-Auth-Request-Email`
   exactly as for a cookie session. The API needs no changes.
2. `--bearer-token-login-fallback=false` — refuse an unverifiable token with
   `403` instead of a login redirect, so `401` (no credential) and `403` (bad
   credential) are distinguishable by a non-browser client.
3. `authRequestHeaders` on the `forward-auth` middleware must include
   `Authorization`. **Without it Traefik drops the token before oauth2-proxy
   sees it and the other two settings do nothing** — every API request looks
   anonymous no matter how the Keycloak clients are configured.

There is deliberately **no `--oidc-extra-audience`**. oauth2-proxy always
accepts its own client ID as an audience, and the `freepod-api-*` scopes in
`tf/deps` inject exactly that. If a token ever fails audience verification, fix
the mapper — do not widen the allowance to `account`, which every token in the
realm carries and which would make any realm token a valid Freepod credential.

`authResponseHeaders` lists `Authorization` and acts as a **sanitizer**: Traefik
overwrites each listed header with the auth response's value and removes it when
the auth response sets none, so the client's raw bearer token never reaches the
API. Removing it from that list would forward the client's header untouched.

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
