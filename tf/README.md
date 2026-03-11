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
  `oauth2_proxy_client_secret`, `oauth2_proxy_cookie_secret`
- `tf/deps/secrets.auto.tfvars`: `keycloak_admin_password`
