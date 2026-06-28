## MODIFIED Requirements

### Requirement: The reconciler injects a system-controlled caelus.tls values block
The deployment reconciler (`api/app/services/reconcile.py`) SHALL compute a `caelus.tls` Helm
values block per deployment and merge it as a system override (highest precedence, via
`merge_values_scoped`), mirroring the existing `_build_plan_overrides` pattern. The block SHALL
classify the deployment hostname as **wildcard** (ends with a configured
`settings.wildcard_domains` entry) or **custom**, reusing the classification logic shape from
`hostnames.py`. Issuer and secret names SHALL come from settings
(`api/app/config.py`: `tls_cluster_issuer`, `acme_email`, `wildcard_tls_secret`), never hardcoded
in chart sources. When a hostname is present, the block SHALL also include a derived **`url`**
field set to `https://<host>` — the canonical public HTTPS URL of the deployment — for both
wildcard and custom hosts, so any chart that needs the full URL (not just the bare host) can
consume it.

#### Scenario: Wildcard host injection
- **WHEN** a deployment hostname ends with a configured wildcard domain (e.g. `hw.freepod.eu`)
- **THEN** `caelus.tls` has `enabled: true`, `wildcard: true`, and `host` set
- **AND** `caelus.tls.url` is set to `https://<host>`
- **AND** no per-app issuer or TLS secret is required (the host is served by Traefik's default
  cert store)

#### Scenario: Custom-domain host injection
- **WHEN** a deployment hostname is a custom domain (e.g. `app.example.com`)
- **THEN** `caelus.tls` has `enabled: true`, `wildcard: false`, `host` set, `issuer` set to the
  HTTP-01 ClusterIssuer name, and `secretName` set to `<release-name>-tls`
- **AND** `caelus.tls.url` is set to `https://<host>`

#### Scenario: Hostname-less deployment
- **WHEN** a deployment has no hostname
- **THEN** no `caelus.tls` block is injected at all (no `host`, no `url`)

## ADDED Requirements

### Requirement: The reconciler projects the derived URL into template-declared value paths
The reconciler SHALL support a per-template, opt-in declaration that names one or more Helm value
paths to populate from the deployment's derived `https://<host>` URL. For each declared path, the
reconciler MUST write the derived URL into the merged Helm values as a system override (winning
over template defaults and user values), using dotted-path projection. This mechanism MUST remain
product-agnostic: the reconciler SHALL NOT contain any chart-specific or product-specific branch;
the destination path(s) come only from the template's declaration. The reserved declaration key
MUST NOT appear in the rendered Helm release. When the deployment has no hostname, the reconciler
SHALL NOT project any URL.

#### Scenario: Vaultwarden template projects DOMAIN from the derived URL
- **WHEN** a vaultwarden deployment has a hostname and its template declares the value path
  `vaultwarden.vaultwarden.domain` as a derived-URL target
- **THEN** the merged Helm values contain `vaultwarden.vaultwarden.domain` set to `https://<host>`
- **AND** the upstream gissilabs `vaultwarden` deployment renders the `DOMAIN` env with that value
- **AND** the reserved declaration key is absent from the merged values handed to Helm

#### Scenario: Template without a declaration is unaffected
- **WHEN** a deployment's template declares no derived-URL target paths
- **THEN** the merged Helm values contain no projected URL beyond `caelus.tls.url`

#### Scenario: Declared target but no hostname
- **WHEN** a deployment's template declares a derived-URL target path but the deployment has no
  hostname
- **THEN** the reconciler projects nothing into that path
