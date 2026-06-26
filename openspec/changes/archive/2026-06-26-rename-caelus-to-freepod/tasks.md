## 1. UI Copy

- [x] 1.1 `ui/index.html`: change `<title>` from "Caelus Control" to "Freepod"
- [x] 1.2 `ui/src/components/AppShell.tsx`: change header `<Typography>` from "Caelus Control" to "Freepod"
- [x] 1.3 `ui/src/components/AppShell.tsx`: change logo `alt` from "Caelus" to "Freepod"
- [x] 1.4 `ui/src/components/HostnameField.tsx`: change `not_resolving` label from "Does not resolve to Caelus" to "Does not resolve to Freepod"
- [x] 1.5 `api/app/main.py`: change FastAPI `title` from "Caelus Deploy" to "Freepod"

## 2. Terraform — App Domain

- [x] 2.1 `tf/app/locals.tf`: change prod domain from `app.deprutser.be` to `freepod.eu`
- [x] 2.2 `tf/app/locals.tf`: change dev domain from `dev.deprutser.be` to `dev.freepod.eu`
- [x] 2.3 `tf/app/prod.tfvars`: change `domain` value from `"app.deprutser.be"` to `"freepod.eu"`
- [x] 2.4 `tf/app/variables.tf`: change `smtp_username` default from `caelus@deprutser.be` to `noreply@freepod.eu`

## 3. Terraform — Keycloak / Auth Domain

- [x] 3.1 `tf/deps/main.tf`: change Keycloak module `domain` from `"app.deprutser.be"` to `"freepod.eu"`
- [x] 3.2 `tf/app/login/main.tf`: change `oidc-issuer-url` from `https://keycloak.app.deprutser.be/realms/master` to `https://keycloak.freepod.eu/realms/master`
- [x] 3.3 `tf/app/login/main.tf`: change `backend-logout-url` from `https://keycloak.app.deprutser.be/realms/master/...` to `https://keycloak.freepod.eu/realms/master/...`

## 4. Deploy

- [x] 4.1 Verify DNS: `freepod.eu`, `dev.freepod.eu`, `keycloak.freepod.eu`, `login.freepod.eu` all resolve to the load balancer
- [x] 4.2 Verify SPF/DKIM records for `freepod.eu` authorize the configured SMTP relay
- [x] 4.3 `cd tf/deps && terraform apply` — Keycloak restarts with `KC_HOSTNAME_URL=keycloak.freepod.eu`
- [x] 4.4 Wait for Keycloak pod to reach `Running` state
- [x] 4.5 `cd tf/app && terraform apply` — app switches to `freepod.eu`, oauth2-proxy updated
- [x] 4.6 Smoke test: load `https://freepod.eu`, authenticate, confirm email sender shows `noreply@freepod.eu`
