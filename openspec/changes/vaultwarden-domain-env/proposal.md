## Why

Vaultwarden needs a **`DOMAIN`** environment variable set to the full HTTPS URL of the
deployment (e.g. `https://vw.example.com`) for its admin portal, email invitation links, and
WebAuthn 2FA to work. The gissilabs upstream chart only emits the `DOMAIN` env from its
`vaultwarden.vaultwarden.domain` value (`templates/deployment.yaml`:
`{{- if .Values.vaultwarden.domain }} - name: DOMAIN ...`).

Today the Caelus `vaultwarden-wrapper` chart leaves `DOMAIN` **unset** (documented as a known
limitation in `products/vaultwarden/README.md` and in the archived `app-tls-termination`
change, task 5.9). The value is **per-deployment** — `https://<the user's hostname>` — and a
Helm parent/wrapper template **cannot** set subchart values dynamically at render time (Helm
resolves subchart values before templating), so neither the wrapper's static `values.yaml` nor a
wrapper template can carry it. The vault works, but admin/email/WebAuthn features silently do
not.

The reconciler (`api/app/services/reconcile.py`, `_build_tls_overrides`) already computes
`caelus.tls.host` (the bare hostname) from `deployment.hostname`. The same place can derive the
full `https://<host>` URL and inject it at the exact subchart path the upstream needs.

## What Changes

- **Reconciler emits a generic derived URL.** `_build_tls_overrides` adds `caelus.tls.url`
  (`https://<host>`) to the existing `caelus.tls` block, alongside `host`/`wildcard`. This is a
  generic, product-agnostic value (the canonical public URL of the deployment), available to any
  chart — not vaultwarden-special.
- **Reconciler maps the URL into the vaultwarden subchart value via an opt-in convention.** To
  set the upstream's `vaultwarden.vaultwarden.domain` (which a wrapper template cannot reach), the
  reconciler honours a per-template **opt-in** declaration that names value paths to populate from
  the derived URL. The vaultwarden product template opts in, mapping
  `vaultwarden.vaultwarden.domain` ← `caelus.tls.url`. The reconciler stays generic: it injects
  only what a template asks for and knows nothing about vaultwarden specifically.
- **Documentation.** `products/vaultwarden/README.md` "Known limitation" section is updated to
  describe `DOMAIN` now being wired, and how the opt-in mapping is configured on the template.

## Capabilities

### New Capabilities

<!-- None: this change extends the existing app-tls-injection capability. -->

### Modified Capabilities

- `app-tls-injection`: the reconciler-injected `caelus.tls` block gains a derived **`url`**
  (`https://<host>`), and the reconciler gains a generic, opt-in mechanism to project that URL
  into a template-declared subchart value path (used by vaultwarden to populate the upstream
  `DOMAIN` env), without product-specific logic in the reconciler.

## Impact

- **Backend:** `api/app/services/reconcile.py` (`_build_tls_overrides` adds `caelus.tls.url`; a
  new opt-in URL-projection step in `_build_system_overrides`/`_build_merged_values`). Possibly a
  small helper for path injection (reuse `app/util.py:set_value_at_path`). New unit tests.
- **Data:** the vaultwarden `ProductTemplateVersion` gains the opt-in declaration (in
  `system_values_json` or an equivalent template field) mapping `vaultwarden.vaultwarden.domain`
  to the derived URL. No DB schema change if carried in existing JSON; a schema/migration is
  needed only if a new template column is chosen (see `design.md` D2).
- **Charts:** none required for vaultwarden — the upstream subchart already renders `DOMAIN` from
  `vaultwarden.vaultwarden.domain`. The wrapper `values.yaml` comment about the limitation is
  updated. No chart version bump strictly required (value is injected at install time), though the
  README note is refreshed.
- **Docs:** `products/vaultwarden/README.md` "Known limitation" → "DOMAIN wiring".
- **No user-visible behavior change** beyond admin portal, email invitation links, and WebAuthn
  2FA now functioning on vaultwarden deployments.
