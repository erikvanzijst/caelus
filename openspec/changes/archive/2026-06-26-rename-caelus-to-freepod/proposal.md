## Why

The product is being rebranded from Caelus to Freepod. All user-facing surfaces — UI copy, browser title, the production domain, and the email sender address — need to reflect the new name. Internal identifiers (code symbols, DB schema, env vars, K8s namespaces, container images) are deliberately left unchanged to keep the change low-risk.

## What Changes

- **UI title and header**: "Caelus Control" → "Freepod" in browser tab and app bar
- **Logo alt text**: "Caelus" → "Freepod"
- **Hostname error message**: "Does not resolve to Caelus" → "Does not resolve to Freepod"
- **FastAPI docs title**: "Caelus Deploy" → "Freepod"
- **Production domain**: `app.deprutser.be` → `freepod.eu`
- **Dev domain**: `dev.deprutser.be` → `dev.freepod.eu`
- **Keycloak hostname**: `keycloak.app.deprutser.be` → `keycloak.freepod.eu`
- **SMTP sender address default**: `caelus@deprutser.be` → `noreply@freepod.eu`

Not changed: Python class names, localStorage keys, DB schema, env var names, Helm values namespace (`caelus.plan.*`), K8s namespace names (`caelus`, `caelus-dev`), container image names, OAuth2 `clientID`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No spec-level behavior changes — this is a brand name and domain substitution only.

## Impact

- **UI**: `ui/index.html`, `ui/src/components/AppShell.tsx`, `ui/src/components/HostnameField.tsx`
- **API**: `api/app/main.py`
- **Terraform (app)**: `tf/app/locals.tf`, `tf/app/prod.tfvars`, `tf/app/variables.tf`, `tf/app/login/main.tf`
- **Terraform (deps)**: `tf/deps/main.tf`
- **Deployment sequence**: `tf/deps` must be applied before `tf/app` so Keycloak restarts with the new hostname URL before oauth2-proxy is reconfigured to point at it. Brief auth outage expected; acceptable.
- **Prerequisites already in place**: DNS records for `freepod.eu` and `dev.freepod.eu` resolve to the load balancer; `*.freepod.eu` and `*.dev.freepod.eu` TLS certs are active at the LB; `noreply@freepod.eu` email address exists.
