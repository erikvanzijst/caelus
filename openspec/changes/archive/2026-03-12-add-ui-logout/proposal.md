## Why

Caelus has no logout functionality. Authentication is managed by oauth2-proxy
(session cookie) in front of Keycloak (OIDC identity provider), but there is no
way for a user to end their session. The email chip in the top-right corner of
the UI is a static, non-interactive element.

Simply clearing the oauth2-proxy session cookie is insufficient: Keycloak
retains an active SSO session, so any page reload silently re-authenticates the
user through Keycloak and issues a new proxy cookie — effectively making the
"logout" a no-op.

A proper logout must terminate **both** the oauth2-proxy session cookie **and**
the Keycloak SSO session in a single user action.

## What Changes

- Add `--backend-logout-url` to the oauth2-proxy Helm deployment, pointing at
  Keycloak's OIDC `end_session_endpoint` with an `{id_token}` placeholder.
  oauth2-proxy substitutes the real token server-side and calls Keycloak before
  clearing its own cookie — the token never reaches the browser.
- Add a Traefik `IngressRoute` in the login namespace that matches
  `Host(var.domain) && PathPrefix(/oauth2/sign_out)` and routes directly to the
  oauth2-proxy service **without** the forward-auth / oauth-errors middleware
  chain. This lets the frontend use a same-origin relative URL (`/oauth2/sign_out`)
  instead of navigating to the `login.*` subdomain.
- Replace the static MUI `Chip` in `AppShell.tsx` with a clickable dropdown
  menu containing a **Logout** option.
- In production (no localStorage auth headers), the logout action navigates the
  browser to `/oauth2/sign_out?rd=<origin>/` which triggers the full
  server-side Keycloak logout, cookie clear, and redirect back to the app where
  the auth middleware sends the user to the Keycloak login page.
- In local development (localStorage auth headers present), the logout action
  clears the stored headers and reloads the page, which re-triggers the email
  dialog.

## Capabilities

### New Capabilities
- `logout-infrastructure`: Terraform configuration for oauth2-proxy
  backend-logout-url and the Traefik IngressRoute exposing `/oauth2/sign_out`
  on the application domain.
- `logout-ui`: Frontend dropdown menu with environment-aware logout behavior.

### Modified Capabilities
- None.

## Impact

- Terraform (`tf/app/login/`): New `--backend-logout-url` extraArg and new
  `IngressRoute` manifest.
- UI (`ui/src/components/AppShell.tsx`): Chip replaced with dropdown menu.
- UI (`ui/src/state/useAuthEmail.ts`): May need a `clearHeaders()` export for
  the logout action.
- Keycloak admin: `caelus-dev` client needs valid post-logout redirect URIs
  registered (`https://app.deprutser.be/`, `https://dev.deprutser.be/`). This
  is a manual admin console change, not code.
