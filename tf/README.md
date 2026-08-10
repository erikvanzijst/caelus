# Terraform Infrastructure

This directory contains the Terraform infrastructure for Caelus, split into
two independent root modules:

- **`app/`** -- The Caelus application (API, UI, worker, OAuth2-proxy).
  Uses Terraform workspaces for dev/prod separation.
- **`deps/`** -- Shared singleton dependencies (Keycloak, Echo).
  No workspaces; single instance shared across all environments.

Both projects deploy to the same Kubernetes cluster using the kubeconfig at
`../k8s/kubeconfigs/dev-k3s.yaml`.

## Why Two Projects?

Keycloak and Echo are cluster-wide singletons that must not be duplicated
when switching between dev and prod workspaces. Separating them into their
own Terraform root module (`deps/`) ensures they have independent state and
lifecycle from the workspace-multiplexed app resources.

## Deploy Order

Shared dependencies must exist before the app:

```bash
# 1. Deploy shared dependencies (one-time, no workspaces)
cd tf/deps
terraform init
terraform apply

# 2. Deploy the app (dev)
cd tf/app
terraform init
terraform apply

# 3. Deploy the app (prod)
terraform workspace select prod || terraform workspace new prod
terraform apply
```

## Secrets

Each project has its own `secrets.auto.tfvars` (gitignored):

- `tf/app/secrets.auto.tfvars`: `db_password`, `smtp_password`,
  `oauth2_proxy_client_ids`, `oauth2_proxy_client_secrets`,
  `oauth2_proxy_cookie_secret`
- `tf/deps/secrets.auto.tfvars`: `keycloak_admin_password`, `smtp_*`,
  `cloudflare_*`, `grafana_admin_password`

`oauth2_proxy_client_ids` and `oauth2_proxy_client_secrets` are **maps keyed
by workspace name**, not scalars — Terraform auto-loads `*.auto.tfvars` for
every workspace, so a scalar cannot express two per-environment values:

```hcl
oauth2_proxy_client_ids = {
  default = "freepod-dev"   # NOTE: the dev workspace is named `default`
  prod    = "freepod-prod"
}
```

Read the secrets with `terraform output -raw freepod_dev_client_secret` (and
`…_prod_…`) in `tf/deps`. Grafana's OIDC client ID and secret need no tfvar at
all: `tf/deps` wires them straight from the Terraform-managed client.

## Keycloak configuration is Terraform-owned

The `freepod` realm and its clients, client scopes and groups are declared in
`tf/deps/keycloak-config/` using the `keycloak/keycloak` provider. **Edits
made in the Keycloak admin console to any managed attribute are reverted on
the next `terraform apply` in `tf/deps`.** Change realm settings, client
settings, scopes and group *definitions* in code.

Two things are deliberately **not** Terraform-managed and are safe to change
by hand:

- **End-user accounts.** No `keycloak_user` resource exists. Users live in
  Keycloak's own Postgres; self-registration and account deletion produce no
  configuration drift.
- **Group membership.** Terraform owns the groups, not who is in them, so
  granting someone `freepod-dev` or `freepod-observability` access needs no
  apply.

The provider is pinned `~> 5.7.0`. From 5.8.0 it sends `bruteForceStrategy`,
a Keycloak 26 field that Keycloak 24 rejects outright, so raising the cap
requires upgrading Keycloak first. See `tf/deps/providers.tf`.
