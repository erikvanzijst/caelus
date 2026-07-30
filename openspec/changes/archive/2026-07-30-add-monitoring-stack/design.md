## Context

Caelus deploys to a single-node k3s cluster. Terraform is split into
`tf/deps/` (cluster-wide singletons: Keycloak, cert-manager, the self-managed
Traefik, and the mailer relay — one shared instance, no workspaces) and
`tf/app/` (per-env dev/prod app resources, including oauth2-proxy). This stack
is cluster-wide and therefore belongs in `tf/deps/`, deployed before `tf/app/`.

A working reference already exists in the homelab repo
(`github.com/erikvanzijst/homelab`, `apps/loki` + `apps/prometheus`): Loki +
Promtail, the Prometheus chart (node-exporter + kube-state-metrics +
Alertmanager) with a forked `scrape_configs.yaml` and alert rules, and Grafana
with pre-wired datasources. The design here ports that reference and retunes it
for Caelus's domain (`freepod.eu`), its self-managed Traefik, and its existing
`keycloak` and `mailer` deps modules.

The homelab reference protects Grafana/Prometheus/Alertmanager with a
cluster-wide oauth2-proxy + Traefik forward-auth. Caelus's equivalent
forward-auth lives in `tf/app/login` — per-env, namespaced to the app, issuing a
host-only cookie on the app apex, and deployed *after* `tf/deps/`. It cannot be
reused here (wrong layer, wrong namespace, wrong cookie host). Keycloak,
however, is already a `tf/deps` singleton, which reshapes the auth approach.

### Where this lives and what it depends on

This stack is a **cluster-wide singleton in `tf/deps/`** (the `monitoring`
namespace), shared across all Caelus environments — it is deliberately *not*
duplicated per caelus-env in `tf/app/`, and it uses no Terraform workspaces.
It has hard runtime dependencies on two other `tf/deps/` singleton modules:

- **`keycloak`** (`keycloak.freepod.eu`) — Grafana authenticates against it via
  OIDC, and the user whitelist is a Keycloak group. Grafana login stays
  (safely) broken until Keycloak and its `grafana` client/group/mapper exist.
- **`mailer`** (`smtp.mailer.svc.cluster.local:25`) — Alertmanager relays all
  alert email through it; the monitoring module carries no external SMTP creds
  of its own.

Both are already deployed in `tf/deps/`, so ordering within `tf/deps` is the
only concern (the Helm releases tolerate the relay/Keycloak coming up
concurrently and reconciling). Nothing in `tf/app/` depends on this stack, so it
can be added or removed independently of the app deployments.

## Goals / Non-Goals

**Goals:**
- Searchable pod logs (Loki + Promtail) with parsed Traefik access logs.
- Node CPU/mem/net/disk and workload state visible in Grafana.
- Email alerts when pods/nodes/cronjobs fail.
- Grafana access restricted to a whitelist of specific users, authenticated by
  the existing Keycloak.
- Stay close to the proven homelab configuration to minimize risk.

**Non-Goals:**
- Exposing Prometheus or Alertmanager publicly (ClusterIP + port-forward only).
- Backing up the Grafana PVC (no `borg` module exists in `tf/deps`; dashboards
  and datasources are reprovisioned from Terraform).
- Managing Keycloak realm objects in Terraform (no Keycloak provider here).
- High-availability / multi-node scaling of any component.

## Decisions

### Location & layout: mirror homelab, land in `tf/deps/`
Two new modules: `tf/deps/loki/` (Loki + Promtail) and `tf/deps/prometheus/`
(Prometheus + Grafana + ingress + alert/scrape config). Grafana lives inside the
`prometheus` module exactly as in homelab, rather than a standalone `grafana`
module — keeping the port faithful eases future diffs against the reference. A
`monitoring` namespace and `module.loki` / `module.prometheus` blocks are added
to `tf/deps/main.tf`, following the existing `module.mailer` / `module.keycloak`
pattern.
*Alternative considered:* a single flat `monitoring` module. Rejected — the
two-module split matches homelab and keeps the log vs. metrics concerns separable.

### Grafana auth: native Keycloak OIDC + Keycloak-group whitelist
Grafana authenticates via `auth.generic_oauth` against the existing Keycloak
(`https://keycloak.freepod.eu/realms/master`). The whitelist is enforced by
Keycloak group membership: Grafana sets `allowed_groups` (e.g.
`freepod-observability`) plus `role_attribute_path` and
`role_attribute_strict = true`, so a token without the group produces no role
and login is denied. Granting/revoking access is then pure Keycloak group
membership — no Terraform apply, no Grafana user list.
*Alternatives considered:*
- A dedicated oauth2-proxy + forward-auth in `tf/deps` (homelab's model).
  Rejected as more moving parts than needed; Grafana's own OIDC covers the only
  exposed UI.
- Reusing `tf/app/login`'s forward-auth. Impossible — per-env, wrong namespace,
  host-only cookie on the app apex.

### Prometheus & Alertmanager: ClusterIP only
Neither has native authentication, so exposing them would put unauthenticated
UIs on the internet. They remain ClusterIP and are reached via
`kubectl port-forward`. Grafana is the only externally reachable UI.
*Alternative considered:* front them with the same oauth2-proxy. Deferred — not
worth the extra component for tools an operator reaches occasionally.

### Alert email: in-cluster mailer relay
Alertmanager points at `smtp.mailer.svc.cluster.local:25` (no auth, no TLS to
the relay), reusing the credentials the `mailer` module already holds. The
monitoring module needs no external SMTP variables — only `alert_email_to`.
*Alternative considered:* direct external SMTP with its own creds (homelab's
approach). Rejected — it would duplicate secrets already managed by `mailer`.

### Traefik metrics: enable in the system module
Dashboard `25330` needs `traefik_*` series. Caelus's self-managed Traefik has
metrics disabled, so `tf/deps/system/helm/traefik/values.yaml.tftpl` enables the
Prometheus metrics endpoint and stamps `prometheus.io/scrape` annotations on the
Traefik Service. Prometheus's default `kubernetes-service-endpoints` job then
discovers it — no bespoke scrape job. This is the one edit outside the new
modules.

### Single-node tuning: keep homelab's shrink/fork choices
Loki runs `SingleBinary` with all other deployment-mode replicas zeroed and the
memcached caches shrunk; Prometheus uses the forked `scrape_configs.yaml` that
drops high-cardinality control-plane histogram buckets. These are correct for
Caelus's single node and are ported as-is.

### Dashboards as code
Provision `1860` and `25330` via the Grafana chart's `dashboards` /
`dashboardProviders` (gnetId-pinned), so a fresh apply comes up with working
dashboards. A mild divergence from homelab (which imports manually), justified
because Grafana is the sole metrics window here (Prometheus UI isn't routinely open).

## Risks / Trade-offs

- **Keycloak bootstrap is manual and out-of-band** → The `grafana` client,
  `freepod-observability` group, and group-membership mapper are not in
  Terraform. Mitigation: document the `kcadm` steps in `tf/deps/README.md`
  alongside the existing Keycloak theme/realm bootstrap; Grafana login stays
  broken (safely denying access) until the group/mapper exist.
- **Forked `scrape_configs.yaml` drifts from the chart** → It must be reconciled
  whenever the Prometheus chart version bumps. Mitigation: keep the explanatory
  header comment from homelab and note the reconcile step in tasks/README.
- **gnetId dashboards can break across Grafana major versions / need egress at
  load** → Mitigation: pin the Grafana chart version (as homelab does); if a
  dashboard breaks, it is cosmetic and swappable.
- **Single-node resource pressure** → Loki, Prometheus, and Grafana all add
  memory/PVC load to one node. Mitigation: inherit homelab's cache-shrink and
  retention bounds; sizes (`~10Gi` Loki, `5Gi` Grafana, `10d` Prometheus
  retention) are tunable.
- **Cross-module coupling to Traefik** → Enabling metrics touches the ingress
  controller's values. Mitigation: it is an additive `metrics.prometheus` block
  and Service annotation; validate with `terraform plan -target=module.system`
  before applying.

## Migration Plan

1. Ensure `keycloak` and `mailer` deps modules are already deployed.
2. Add new variables to `secrets.auto.tfvars` (`grafana_admin_password`,
   `alert_email_to`, Grafana OIDC client id/secret).
3. Bootstrap Keycloak: create the `grafana` client, the `freepod-observability`
   group, and a group-membership mapper; add the allowed users to the group.
4. `terraform apply` in `tf/deps/` (brings up namespace, Loki, Promtail,
   Prometheus, Grafana, Traefik metrics change).
5. Verify: logs searchable in Grafana; node/pod dashboards populated; a test
   alert emails through the relay; only group members can sign in.

**Rollback:** remove the `module.loki` / `module.prometheus` blocks and the
`monitoring` namespace, and revert the Traefik metrics edit, then `apply`. No
other module depends on the stack, so removal is self-contained.

## Open Questions

- None blocking. Retention/PVC sizes and the exact alert thresholds are ported
  from homelab and can be tuned post-deploy without spec changes.
