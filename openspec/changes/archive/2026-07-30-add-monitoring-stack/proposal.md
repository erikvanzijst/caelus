## Why

The Caelus k3s cluster currently has no centralized observability: pod logs are
only reachable via `kubectl logs` on a per-pod basis, there is no node-level
resource visibility (CPU/memory/network/disk), and nothing alerts an operator
when a pod or deployment starts failing. A single failing workload can go
unnoticed until a user reports it. This change adds a cluster-wide
Loki/Grafana/Prometheus stack — modeled on the proven homelab setup — so logs
are searchable, node and workload health is visible, and failures generate
email alerts.

## What Changes

- Add a cluster-wide `monitoring` namespace and stack in `tf/deps/` (shared
  across all Caelus environments — **not** per caelus-env), wired from
  `tf/deps/main.tf` alongside the existing singleton modules.
- **Log aggregation**: new `tf/deps/loki/` module deploys Loki (SingleBinary,
  filesystem storage) plus a Promtail DaemonSet that ships every pod's logs to
  Loki, including Traefik access-log (CLF) parsing so ingress traffic is
  queryable.
- **Metrics collection**: new `tf/deps/prometheus/` module deploys the
  Prometheus chart, which bundles node-exporter (node CPU/mem/net/disk),
  kube-state-metrics (workload state), and Alertmanager. A forked
  `scrape_configs.yaml` drops high-cardinality control-plane histogram buckets
  for the single-node cluster.
- **Alerting**: Alertmanager rules for `PodCrashLooping`, `NodeDown`,
  `HighMemoryUsage`, and `CronJobFailed`, delivered by email through the
  existing in-cluster mailer relay (`smtp.mailer.svc.cluster.local:25`) — no
  duplicated SMTP credentials.
- **Dashboards & access**: Grafana with Prometheus + Loki datasources and two
  Terraform-managed dashboards (Node Exporter Full `1860`, Kubernetes Traefik
  Ingress NextGen `25330`). Grafana is exposed at `grafana.freepod.eu` and
  authenticates users via native Keycloak OIDC, restricted to members of a
  Keycloak group (whitelist). Prometheus and Alertmanager stay ClusterIP-only
  (reached via `kubectl port-forward`).
- **Traefik metrics**: enable the Prometheus metrics endpoint on the
  self-managed Traefik (`tf/deps/system/helm/traefik`) so dashboard `25330`
  has data to render.

## Capabilities

### New Capabilities
- `pod-log-aggregation`: Collect logs from all pods cluster-wide into a
  searchable Loki store via a Promtail DaemonSet, including parsed Traefik
  access logs.
- `cluster-metrics-collection`: Scrape node, workload, and Traefik metrics into
  Prometheus with single-node-tuned scrape configuration and retention.
- `failure-alerting`: Evaluate alert rules for failing pods/nodes/cronjobs and
  deliver notifications by email through the in-cluster mailer relay.
- `monitoring-dashboards-access`: Provide Grafana with pre-wired datasources and
  managed dashboards, exposed at `grafana.freepod.eu` behind a Keycloak-OIDC
  group whitelist.

### Modified Capabilities
<!-- None. Enabling Traefik's Prometheus metrics is an implementation detail of
     cluster-metrics-collection, not a spec-level behavior change to an existing
     capability. -->

## Impact

- **New Terraform modules**: `tf/deps/loki/`, `tf/deps/prometheus/` (the latter
  also houses Grafana, mirroring the homelab layout).
- **Modified Terraform**: `tf/deps/main.tf` (namespace + module wiring),
  `tf/deps/variables.tf` (new vars), `tf/deps/system/helm/traefik/values.yaml.tftpl`
  (enable Prometheus metrics), `tf/deps/README.md` (docs).
- **New Helm releases**: `loki`, `promtail`, `prometheus`, `grafana` in the
  `monitoring` namespace.
- **New variables / secrets** (`secrets.auto.tfvars`): `grafana_admin_password`
  (sensitive), `alert_email_to`, and Grafana OIDC client id/secret. No external
  SMTP credentials needed (alerts use the relay).
- **Manual bootstrap (one-time, out-of-band)**: a Keycloak `grafana` client, a
  `freepod-observability` group, and a group-membership mapper — there is no
  Keycloak Terraform provider here, so this is documented in the README like the
  existing Keycloak theme/realm bootstrap.
- **Dependencies**: relies on the existing `keycloak` and `mailer` deps modules
  already deployed in `tf/deps/`.
- **Out of scope**: Grafana PVC backup (no `borg` module exists in `tf/deps`);
  exposing Prometheus/Alertmanager via ingress.
