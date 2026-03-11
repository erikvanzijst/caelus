# Shared Dependencies

This Terraform project manages cluster-wide singleton services that are
shared across all Caelus environments (dev and prod). It has its own
independent state and does not use Terraform workspaces.

## What It Creates

- `keycloak` namespace, deployment, Postgres database, PVC, service, ingress
- `echo` namespace, deployment, service, ingress

## Prerequisites

- Terraform `>= 1.0`
- Access to the Kubernetes cluster via `../../k8s/kubeconfigs/dev-k3s.yaml`

## Configuration

Create `secrets.auto.tfvars` (gitignored):

```hcl
keycloak_admin_password = "replace-with-actual-password"
```

## Deploy

```bash
cd tf/deps
terraform init
terraform apply
```

## Notes

- Keycloak always uses the production domain (`keycloak.app.deprutser.be`).
- Echo uses `echo.app.deprutser.be`.
- This project must be deployed before `tf/app/`, since the app's
  OAuth2-proxy depends on a running Keycloak instance.
- Do NOT run `terraform destroy` here without understanding that it will
  take down Keycloak for all environments.
