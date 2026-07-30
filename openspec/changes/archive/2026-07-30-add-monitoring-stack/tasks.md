## 1. Variables & scaffolding

- [x] 1.1 Add `monitoring` namespace resource to `tf/deps/main.tf` (mirror the existing `kubernetes_namespace "mailer"` pattern)
- [x] 1.2 Declare new variables in `tf/deps/variables.tf`: `grafana_admin_password` (sensitive), `alert_email_to`, `grafana_oidc_client_id`, `grafana_oidc_client_secret` (sensitive)
- [x] 1.3 Document the new variables in `tf/deps/secrets.auto.tfvars` (local, gitignored) and add example lines to the README
- [x] 1.4 Reserve the observability hostnames in `api/.env` (`CAELUS_RESERVED_HOSTNAMES`) so users can't claim them. Add both the apex and `dev.freepod.eu` variants of `grafana` (exposed now) plus eager future reservations `prometheus`, `loki`, `alerts`, and `alertmanager` — i.e. `grafana.freepod.eu`, `prometheus.freepod.eu`, `loki.freepod.eu`, `alerts.freepod.eu`, `alertmanager.freepod.eu` and `grafana.dev.freepod.eu`, `prometheus.dev.freepod.eu`, `loki.dev.freepod.eu`, `alerts.dev.freepod.eu`, `alertmanager.dev.freepod.eu` (matching the existing apex+dev reservation convention). Verify `hostnames.py:_check_reserved` then rejects them (returns `reserved`)

## 2. Loki module (pod-log-aggregation)

- [x] 2.1 Create `tf/deps/loki/variables.tf` (`namespace`)
- [x] 2.2 Create `tf/deps/loki/main.tf` `helm_release "loki"`: grafana/loki chart, `SingleBinary` mode, filesystem storage, ~10Gi PVC, `auth_enabled=false`, `replication_factor=1`, v13 tsdb schema, all other deployment-mode replicas zeroed, memcached `chunksCache`/`resultsCache` shrunk for single-node RAM
- [x] 2.3 Add `helm_release "promtail"` (DaemonSet) pushing to `loki.monitoring.svc:3100`, carrying over the homelab `scrapeConfigs` including Kubernetes pod metadata labels and Traefik CLF access-log parsing
- [x] 2.4 Wire `module "loki"` into `tf/deps/main.tf` (source `./loki`, `namespace` = monitoring namespace)

## 3. Prometheus + Alertmanager (cluster-metrics-collection, failure-alerting)

- [x] 3.1 Create `tf/deps/prometheus/variables.tf` (`namespace`, `grafana_admin_password`, `alert_email_to`, `grafana_domain`, `grafana_oidc_client_id`, `grafana_oidc_client_secret`)
- [x] 3.2 Create `tf/deps/prometheus/prometheus.tf` `helm_release "prometheus"` (prometheus-community/prometheus chart) with node-exporter + kube-state-metrics enabled and pushgateway disabled
- [x] 3.3 Add `tf/deps/prometheus/scrape_configs.yaml` (forked from the chart default) dropping high-cardinality apiserver/etcd/workqueue/kubeproxy histogram buckets; include the header comment noting it must be reconciled on chart bumps
- [x] 3.4 Configure Alertmanager to send email via `smtp.mailer.svc.cluster.local:25` (no auth/TLS) to `var.alert_email_to`
- [x] 3.5 Add alerting rules `PodCrashLooping`, `NodeDown`, `HighMemoryUsage`, `CronJobFailed` (+ the cronjob recording rules) mirroring homelab
- [x] 3.6 Keep Prometheus and Alertmanager as ClusterIP (no ingress)

## 4. Grafana (monitoring-dashboards-access)

- [x] 4.1 Create `tf/deps/prometheus/grafana.tf` `helm_release "grafana"` with Prometheus + Loki datasources pre-wired
- [x] 4.2 Configure `auth.generic_oauth` against Keycloak (`https://keycloak.freepod.eu/realms/master`): client id/secret, `allowed_groups = ["freepod-observability"]`, `role_attribute_path`, `role_attribute_strict = true`, and `root_url = https://grafana.freepod.eu`
- [x] 4.3 Provision dashboards as code via the chart's `dashboardProviders`/`dashboards`: Node Exporter Full (`1860`) and Kubernetes Traefik Ingress NextGen (`25330`)
- [x] 4.4 Add `tf/deps/prometheus/ingress.tf` Traefik Ingress for `grafana.freepod.eu` with HSTS (matching other freepod ingresses) and NO forward-auth
- [x] 4.5 Wire `module "prometheus"` into `tf/deps/main.tf` passing namespace + the new variables

## 5. Traefik metrics (cross-module)

- [x] 5.1 Enable `metrics.prometheus` in `tf/deps/system/helm/traefik/values.yaml.tftpl`
- [x] 5.2 Add `prometheus.io/scrape` (+ port/path) annotations to the Traefik Service so Prometheus's `kubernetes-service-endpoints` job discovers it
- [x] 5.3 Verify with `terraform plan -target=module.system` that only additive metrics changes appear

## 6. Docs & Keycloak bootstrap

- [x] 6.1 Update `tf/deps/README.md`: describe the monitoring stack, its namespace, and that it is cluster-wide
- [x] 6.2 Document the one-time Keycloak bootstrap (`kcadm`): create the `grafana` client, the `freepod-observability` group, and a group-membership mapper; add allowed users to the group
- [x] 6.3 Document `kubectl port-forward` access for Prometheus and Alertmanager (no ingress)

## 7. Deploy & verify

- [x] 7.1 `terraform init` + `terraform plan` in `tf/deps/`; review the plan
- [x] 7.2 `terraform apply`; confirm all Helm releases (`loki`, `promtail`, `prometheus`, `grafana`) reach ready
- [x] 7.3 Verify pod logs are searchable in Grafana via the Loki datasource (including a parsed Traefik access-log query)
- [x] 7.4 Verify Node Exporter Full (`1860`) shows node CPU/mem/net/disk and Traefik NextGen (`25330`) renders live data
- [x] 7.5 Trigger/observe a test alert and confirm an email arrives via the mailer relay
- [x] 7.6 Verify a `freepod-observability` member can sign in to Grafana and a non-member is denied
