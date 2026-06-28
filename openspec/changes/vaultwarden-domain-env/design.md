## Context

Caelus deploys user apps as Helm charts via the reconciler
(`api/app/services/reconcile.py`). The reconciler renders Helm values by merging template
defaults + user values + system overrides (`template_values.merge_values_scoped`) and runs
`helm upgrade --install`. System overrides are contributed under the `caelus` namespace by
`_build_system_overrides`, which deep-merges `_build_plan_overrides` (`caelus.plan`) and
`_build_tls_overrides` (`caelus.tls`). `_build_tls_overrides` already derives `caelus.tls.host`
(the bare, lowercased hostname) from `deployment.hostname` and classifies wildcard vs custom.

The **vaultwarden** product uses a wrapper chart (`products/vaultwarden/chart/`,
`vaultwarden-wrapper`) that depends on the upstream gissilabs `vaultwarden` `1.4.0` chart. The
wrapper disables the upstream Ingress and provides its own (`templates/ingress.yaml`) reading
`caelus.tls`, so it can carry per-deployment TLS.

Vaultwarden the application needs `DOMAIN` (the full `https://<host>` URL) for the admin portal,
email invitation links, and WebAuthn 2FA. The upstream chart emits the `DOMAIN` env **only** from
`vaultwarden.vaultwarden.domain` (`templates/deployment.yaml`). That value is per-deployment.

**The Helm constraint:** a parent/wrapper chart cannot set a subchart's values dynamically at
render time — Helm resolves subchart values (subordinate `values.yaml` + parent overrides) *before*
templating, so a wrapper `template` that computes `https://<caelus.tls.host>` cannot write it back
into the subchart's value tree, and cannot inject env into the subchart's already-rendered pod
spec. The only mechanisms that reach the subchart are (a) **static** parent values under the
subchart key, or (b) **install-time `--set`/values supplied by the installer** (the reconciler).
The reconciler is the only actor that holds the per-deployment hostname and can write subchart
values. So the wiring must happen reconciler-side.

The verbatim deployment env contract from upstream (`charts/vaultwarden-1.4.0`):

```
{{- if .Values.vaultwarden.domain }}
- name: DOMAIN
  value: {{ .Values.vaultwarden.domain | quote }}
{{- end }}
```

(i.e. parent path `vaultwarden.vaultwarden.domain`).

## Goals / Non-Goals

**Goals:**
- Set vaultwarden's `DOMAIN` env to `https://<deployment hostname>` per deployment, so admin
  portal, email invitations, and WebAuthn 2FA work.
- Keep the reconciler **generic**: no `if product == "vaultwarden"` branch, no hardcoded subchart
  path in reconciler source. The value and its destination are derived from data the deployment
  already carries (hostname) and from the template's own declaration.
- Reuse the existing `caelus.tls` injection and `merge_values_scoped` precedence model.

**Non-Goals:**
- Changing TLS termination, hostname validation, or wildcard classification (reused as-is).
- Forking/patching the upstream gissilabs chart (it already renders `DOMAIN` from a value).
- Setting `DOMAIN` for non-vaultwarden products (they don't need it); the mechanism is generic
  but opt-in, so only templates that declare it are affected.
- Adding a redirect/scheme decision — the URL is always `https://` (Caelus terminates TLS for all
  app hosts; see `app-tls-termination`).

## Decisions

### D1: Derive `caelus.tls.url` (`https://<host>`) generically in `_build_tls_overrides`

**Decision:** Extend `_build_tls_overrides` to add a `url` key to the `caelus.tls` block:
`caelus.tls.url = "https://" + host`, computed from the same `host` already derived from
`deployment.hostname`. It is emitted whenever a hostname is present (both wildcard and custom
classes), since Caelus serves all app hosts over HTTPS.

**Alternatives considered:**
- *A separate `caelus.url` top-level value.* Rejected: the URL is conceptually part of the
  per-app HTTPS identity already modelled by `caelus.tls` (which owns `host`, `wildcard`,
  `secretName`). Co-locating keeps one source of truth and matches the existing block.
- *Compute the URL in the chart from `caelus.tls.host`.* Works for charts that own their
  templates, but is useless for the vaultwarden subchart `DOMAIN` (the chart-side string can't
  reach the subchart value). Centralizing the derived URL also avoids each chart re-deriving the
  scheme.

**Rationale:** Minimal, additive, and generic. `caelus.tls.url` is a reusable canonical public
URL any chart can consume; it does not mention vaultwarden.

### D2: Reconciler projects the URL into a template-declared value path (opt-in convention)

**Decision:** The reconciler honours a per-template **opt-in declaration** that lists value paths
to populate from the derived URL. The vaultwarden template declares
`vaultwarden.vaultwarden.domain`. At reconcile time, for each declared path, the reconciler writes
the derived `https://<host>` value into the merged Helm values (using
`app/util.py:set_value_at_path`), so the upstream subchart sees
`vaultwarden.vaultwarden.domain` and renders `DOMAIN`. When the deployment has no hostname, no
projection occurs.

The declaration lives in the template's existing JSON (e.g. a reserved key such as
`caelus.derivedUrlPaths: ["vaultwarden.vaultwarden.domain"]` carried in `system_values_json`, or
an equivalent template field), so **no reconciler source change is needed to onboard a future
chart** — a template just declares the paths it wants populated.

**Alternatives considered:**
- *(a) Hardcode `vaultwarden.vaultwarden.domain = url` in the reconciler.* Rejected by the task:
  product-specific logic in a generic reconciler. It would also re-introduce a chart contract in
  Python that the README already warns against.
- *(b) Inject only `caelus.tls.url` and let a chart-side mechanism map it to `DOMAIN`.* Rejected:
  the Helm constraint (Context) means a wrapper template **cannot** push a value into the subchart
  or its pod env. There is no chart-side mechanism that reaches `vaultwarden.vaultwarden.domain` or
  the subchart pod from the parent. So (b) cannot work for this upstream chart.
- *(c) Wrapper adds a `DOMAIN` env via the subchart's `extraEnv`.* `extraEnv` *is* a subchart
  value (`vaultwarden.extraEnv`), so it has the same dynamic-value problem: the wrapper can only
  set it statically, and the reconciler would still have to inject the per-deployment value at
  `vaultwarden.extraEnv.DOMAIN`. That is strictly more complex than (and isomorphic to) setting
  `vaultwarden.vaultwarden.domain` directly, which the upstream already supports — so prefer the
  direct path.
- *(d) A reserved convention key (chosen).* The template declares the destination path(s); the
  reconciler supplies the value. Generic, opt-in, and data-driven.

**Rationale:** Keeps the reconciler product-agnostic while still reaching the subchart value only
the installer can write. The mapping is configuration (template data), not code. Reuses the
existing `set_value_at_path` util and the `merge_values_scoped` precedence (system override wins).

### D3: Where the opt-in declaration is stored

**Decision (recommended):** Carry the declaration in the template's existing
`system_values_json` under a reserved `caelus.derivedUrlPaths` key (a list of dotted paths), so it
travels with the template version and requires **no DB schema/migration**. The reconciler reads
and strips this reserved key before merging values into Helm (so it never leaks into the rendered
release), then projects the derived URL into each listed path.

**Alternatives:** a dedicated nullable column on `ProductTemplateVersionORM` (cleaner typing,
explicit) — but it requires an Alembic migration and API/CLI plumbing for marginal benefit, given
the value is naturally template-scoped JSON. If a typed field is later desired, it is an additive
migration; the spec is written against the *behavior* (project derived URL into declared paths),
not the storage location.

**Rationale:** Minimizes blast radius and keeps API/CLI parity trivial (the declaration is just
template data already round-tripped today).

### D4: Scheme is always `https://`

**Decision:** The derived URL uses the `https://` scheme unconditionally.

**Rationale:** Per `app-tls-termination`, Caelus terminates TLS for every app host (wildcard via
the default cert store, custom via per-app HTTP-01), and the wrapper Ingress is `websecure`-only
with a cluster-wide `:80`→`https` redirect. There is no Caelus app host served over plain HTTP, so
a configurable scheme would be dead complexity.
