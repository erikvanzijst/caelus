# Shared Dependencies

This Terraform project manages cluster-wide singleton services that are
shared across all Caelus environments (dev and prod). It has its own
independent state and does not use Terraform workspaces.

## What It Creates

- `keycloak` namespace, deployment, Postgres database, PVC, service, ingress.
  Keycloak runs a **custom image** (`var.keycloak_image`) with the Freepod
  login/account/email theme baked in — see [Keycloak theming](#keycloak-theming).
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

## Keycloak theming

Keycloak's login, account console and transactional emails are themed to match
the freepod.eu landing page (dark "digital sovereignty" look, Fraunces/Schibsted
Grotesk type, gradient CTAs).

### Where the theme lives

```
keycloak/theme/freepod/
  login/     # FreeMarker + CSS: sign-in, register, reset, OTP, errors
  account/   # PatternFly-v4 SPA skin: profile / "Personal info" pages
  email/     # FreeMarker: password reset, verify email, admin actions
```

Each type has its own `resources/` (the fonts are self-hosted per type, copied
from the UI's `@fontsource` packages — no Google Fonts calls). One stylesheet
per type rebrands every screen of that type, because all screens share the
type's `template.ftl`.

### How it's deployed (production)

The theme is **baked into the Keycloak image** rather than mounted (it's ~22
files / ~400KB — too much for a ConfigMap). `keycloak/Dockerfile` is just
`FROM quay.io/keycloak/keycloak:24.0` + `COPY theme/freepod`. Build, push and
roll out:

```bash
./scripts/build-images.sh --keycloak     # build + push ghcr.io/<owner>/caelus/keycloak
cd tf/deps && terraform apply            # if var.keycloak_image / digest changed
kubectl rollout restart deployment/keycloak -n keycloak
```

The deployment references `var.keycloak_image`
(default `ghcr.io/erikvanzijst/caelus/keycloak:latest`).

### Assigning the theme to the realm

Baking the theme into the image only makes it *available*; the realm must select
it. This is realm config (not managed in Terraform — there's no Keycloak
provider here), so set it once per realm via the admin console
(Realm settings → Themes → Login/Account/Email theme = `freepod`) or via
`kcadm`:

```bash
kcadm.sh update realms/master -s loginTheme=freepod -s accountTheme=freepod -s emailTheme=freepod
```

### Local theme development

There is no Keycloak in the local dev stack, so iterate against a **throwaway
Keycloak container**. Two quirks of running Docker from inside the dev container
(sibling containers via the mounted Docker socket) shape the commands below:

- **Bind-mount sources are *host* paths**, not dev-container paths — so we mount
  the host directory backing `/workspace`.
- **Port publishing happens on the host**, where the dev container already owns
  the forwarded ports (`8501`, `8000`). So instead of `-p`, the throwaway
  containers **share the dev container's network namespace**
  (`--network container:<devcontainer>`) and listen on those ports directly.

```bash
DEVCTR=caelus-app-1   # this dev container, as the Docker host sees it
HOST_WS=$(docker inspect "$DEVCTR" --format \
  '{{range .Mounts}}{{if eq .Destination "/workspace"}}{{.Source}}{{end}}{{end}}')

docker run -d --name freepod-kc \
  --network "container:$DEVCTR" \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  -v "$HOST_WS/tf/deps/keycloak/theme/freepod:/opt/keycloak/themes/freepod:ro" \
  quay.io/keycloak/keycloak:24.0 \
  start-dev --http-port=8501 \
    --spi-theme-cache-themes=false --spi-theme-cache-templates=false \
    --spi-theme-static-max-age=-1
```

Then point the `master` realm at the theme and add a permissive client so the
login/account pages can be opened directly (`start-dev` uses an **in-memory DB**,
so this must be re-applied after every restart):

```bash
K="docker exec freepod-kc /opt/keycloak/bin/kcadm.sh"
$K config credentials --server http://localhost:8501 --realm master --user admin --password admin
$K update realms/master -s loginTheme=freepod -s accountTheme=freepod -s emailTheme=freepod \
    -s registrationAllowed=true -s resetPasswordAllowed=true
$K create clients -r master -s clientId=theme-preview -s enabled=true -s publicClient=true \
    -s standardFlowEnabled=true -s 'redirectUris=["*"]' -s 'webOrigins=["*"]'
```

Preview from the host (forwarded on `8501`):

- **Login** (and register / forgot-password): `http://localhost:8501/realms/master/protocol/openid-connect/auth?client_id=theme-preview&response_type=code&scope=openid&redirect_uri=http://localhost:8501/`
- **Account**: `http://localhost:8501/realms/master/account/` (sign in as `admin`/`admin`)

> **Caching gotcha.** Keycloak caches theme *resources* in memory even with
> `--spi-theme-cache-themes=false`. Login-CSS edits show on a normal reload, but
> account/email resource changes may keep serving stale bytes — recreate the
> container (`docker rm -f freepod-kc` + the `run` above) to flush, and add a
> `?cb=1` query to the URL so the browser refetches the new resource-version URL.

#### Previewing emails (Mailpit)

Emails are only produced by sending over SMTP — there's no in-browser preview.
Run [Mailpit](https://mailpit.axllent.org/) as a local SMTP sink (web inbox on
the forwarded `8000`):

```bash
docker run -d --name freepod-mailpit --network "container:$DEVCTR" \
  -e MP_SMTP_BIND_ADDR=0.0.0.0:1025 -e MP_UI_BIND_ADDR=0.0.0.0:8000 \
  axllent/mailpit
```

Point the realm's SMTP at it and give the test user an email address (kcadm
can't set the SMTP map, so use the REST API for that part):

```bash
TOKEN=$(curl -s -d client_id=admin-cli -d username=admin -d password=admin \
  -d grant_type=password \
  http://localhost:8501/realms/master/protocol/openid-connect/token | \
  python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -s -X PUT http://localhost:8501/admin/realms/master \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"smtpServer":{"host":"localhost","port":"1025","from":"no-reply@freepod.eu","fromDisplayName":"Freepod","ssl":"false","starttls":"false","auth":"false"}}'

AID=$($K get users -r master -q username=admin --fields id --format csv --noquotes | head -1)
$K update users/$AID -r master -s email=admin@freepod.eu -s emailVerified=true
```

Trigger sends, then read the rendered HTML at `http://localhost:8000`:

```bash
# password reset: use "Forgot Password?" on the login page, OR trigger admin emails:
curl -s -X PUT "http://localhost:8501/admin/realms/master/users/$AID/send-verify-email" \
  -H "Authorization: Bearer $TOKEN"
curl -s -X PUT "http://localhost:8501/admin/realms/master/users/$AID/execute-actions-email" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '["UPDATE_PASSWORD"]'
```

#### Cleanup

```bash
docker rm -f freepod-kc freepod-mailpit
```

## Notes

- Keycloak always uses the production domain (`keycloak.freepod.eu`).
- Echo uses `echo.freepod.eu`.
- This project must be deployed before `tf/app/`, since the app's
  OAuth2-proxy depends on a running Keycloak instance.
- Do NOT run `terraform destroy` here without understanding that it will
  take down Keycloak for all environments.
