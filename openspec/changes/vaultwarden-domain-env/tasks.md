## 1. Reconciler: derive `caelus.tls.url`

- [ ] 1.1 In `api/app/services/reconcile.py`, extend `_build_tls_overrides` to add
      `url: "https://" + host` to the `caelus.tls` block (emitted for both wildcard and custom
      hosts; omitted only when the deployment has no hostname, like the rest of the block).
- [ ] 1.2 Unit tests: a deployment with a hostname yields `caelus.tls.url == "https://<host>"`
      (lowercased host); a hostname-less deployment yields no `caelus.tls` block (unchanged).

## 2. Reconciler: opt-in URL projection into declared paths

- [ ] 2.1 Define the reserved opt-in declaration key (recommended:
      `caelus.derivedUrlPaths` — a list of dotted value paths — carried in the template's
      `system_values_json`). Document the key shape in a code comment.
- [ ] 2.2 In `_build_merged_values`/`_build_system_overrides`, read the declared paths from the
      template, and for each path write the derived `https://<host>` URL into the merged Helm
      values via `app/util.py:set_value_at_path`. Strip the reserved key so it never reaches the
      rendered release. Skip entirely when the deployment has no hostname.
- [ ] 2.3 Ensure the system override precedence is preserved (the projected value wins over
      template defaults and user values, consistent with `merge_values_scoped`).
- [ ] 2.4 Unit tests: a template declaring `vaultwarden.vaultwarden.domain` produces merged
      values with `vaultwarden.vaultwarden.domain == "https://<host>"`; a template with no
      declaration is unaffected; a declared template on a hostname-less deployment injects nothing;
      the reserved declaration key does not appear in the merged output.

## 3. Vaultwarden template wiring (data)

- [ ] 3.1 Add the opt-in declaration to the vaultwarden `ProductTemplateVersion`
      (`system_values_json` reserved key `caelus.derivedUrlPaths: ["vaultwarden.vaultwarden.domain"]`),
      so the reconciler projects the derived URL into the upstream subchart value.
- [ ] 3.2 Verify (e.g. via the existing render/merge path or a `helm template` dry run using the
      reconciler-merged values) that the upstream `vaultwarden-1.4.0` deployment renders
      `- name: DOMAIN` with the per-deployment `https://<host>` value.

## 4. Documentation

- [ ] 4.1 Update `products/vaultwarden/README.md`: replace the "Known limitation" note about
      `DOMAIN` being unset with a "DOMAIN wiring" note describing the reconciler-injected
      `caelus.tls.url` and the template's `caelus.derivedUrlPaths` opt-in mapping to
      `vaultwarden.vaultwarden.domain`.
- [ ] 4.2 Update the comment in `products/vaultwarden/chart/values.yaml` that currently says
      `DOMAIN ... is intentionally left unset` to reflect that it is now injected at reconcile
      time.

## 5. Validation

- [ ] 5.1 Run the API test suite (`uv run --no-sync pytest`) — new and existing reconcile tests
      pass.
- [ ] 5.2 Live (operator) smoke check on a vaultwarden deployment: admin portal loads, an email
      invitation link points at `https://<host>`, and WebAuthn 2FA registration succeeds.
- [ ] 5.3 `openspec validate vaultwarden-domain-env` reports valid; archive on completion.
