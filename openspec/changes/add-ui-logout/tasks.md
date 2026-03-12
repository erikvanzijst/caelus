## 1. Terraform — oauth2-proxy backend logout

- [x] 1.1 Add `backend-logout-url` to `extraArgs` in `tf/app/login/main.tf`:
      `backend-logout-url = "https://keycloak.app.deprutser.be/realms/master/protocol/openid-connect/logout?id_token_hint={id_token}"`
- [x] 1.2 Verify `whitelist_domains` includes `var.domain` (already present;
      confirm it covers the `rd` redirect target)

## 2. Terraform — Traefik IngressRoute for sign_out

- [x] 2.1 Add a `kubernetes_manifest` resource for a Traefik `IngressRoute` in
      `tf/app/login/main.tf` that matches
      `Host(\`${var.domain}\`) && PathPrefix(\`/oauth2/sign_out\`)` and routes
      to the `oauth2-proxy` service on port 8080, with no middleware
- [x] 2.2 Set `entryPoints` to `["web", "websecure"]` to match the Caelus
      ingress

## 3. Keycloak — client configuration (manual)

- [ ] 3.1 (manual) In Keycloak admin console, open the `caelus-dev` client
      under the `master` realm
- [ ] 3.2 (manual) Add `https://app.deprutser.be/` and
      `https://dev.deprutser.be/` to **Valid Post Logout Redirect URIs**

## 4. Frontend — useAuthEmail clearHeaders

- [x] 4.1 Export a `clearStoredAuthHeaders()` function from
      `ui/src/state/useAuthEmail.ts` that removes the `caelus.auth.headers`
      key from localStorage

## 5. Frontend — logout dropdown menu

- [x] 5.1 In `ui/src/components/AppShell.tsx`, replace the static `Chip` with a
      clickable element (MUI `Chip` with `onClick` or a `Button`) that opens an
      MUI `Menu`
- [x] 5.2 Add a `Logout` `MenuItem` to the menu
- [x] 5.3 Implement the logout handler:
      - If `getStoredAuthHeaders()` is non-empty (local dev): call
        `clearStoredAuthHeaders()`, then `window.location.reload()`
      - Otherwise (production): set `window.location.href` to
        `/oauth2/sign_out?rd=` + `encodeURIComponent(window.location.origin + '/')`
- [x] 5.4 Add necessary MUI imports (`Menu`, `MenuItem`, and `useState` for
      anchor element)

## 6. Deploy and verify

- [x] 6.1 Apply Terraform changes (`tf/app/`) in the dev workspace
- [x] 6.2 Verify the IngressRoute is created and `/oauth2/sign_out` on
      `dev.deprutser.be` routes to oauth2-proxy (curl or browser)
- [x] 6.3 Build and deploy the updated UI
- [x] 6.4 End-to-end test: log in, click Logout, confirm landing on Keycloak
      login page, confirm re-login requires credentials (Keycloak session was
      terminated)
- [x] 6.5 Test local dev: start UI with `npm run dev`, enter email in dialog,
      click Logout, confirm dialog reappears
