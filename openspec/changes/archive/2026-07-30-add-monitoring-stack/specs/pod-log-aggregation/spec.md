## ADDED Requirements

### Requirement: Cluster-wide pod log collection

The system SHALL collect logs from all pods across all namespaces in the k3s
cluster and ship them to a central Loki store, deployed cluster-wide in the
`monitoring` namespace (not per caelus-env).

#### Scenario: Logs from a new pod become available

- **WHEN** a pod in any namespace writes to stdout/stderr
- **THEN** a Promtail DaemonSet running on that pod's node reads the container
  log file and pushes the entries to Loki within seconds

#### Scenario: Logs are labeled for querying

- **WHEN** Promtail forwards a log line to Loki
- **THEN** the stream carries the `namespace`, `app`, `pod`, and `container`
  labels derived from Kubernetes pod metadata

### Requirement: Searchable log store

The system SHALL run Loki in single-binary mode with filesystem-backed
persistent storage, retaining logs for the configured period and serving
queries to Grafana.

#### Scenario: Operator searches logs in Grafana

- **WHEN** an operator queries a LogQL expression against the Loki datasource in
  Grafana
- **THEN** matching log lines from the selected namespace/app/pod are returned

#### Scenario: Logs survive a Loki pod restart

- **WHEN** the Loki pod is restarted or rescheduled
- **THEN** previously ingested logs remain available because the store is backed
  by a persistent volume

### Requirement: Parsed Traefik access logs

The system SHALL parse Traefik access logs (Common Log Format) so ingress
requests are queryable by structured fields rather than raw text.

#### Scenario: Ingress request is queryable by status and route

- **WHEN** Traefik emits an access-log line for an incoming request
- **THEN** Promtail extracts fields such as HTTP method, status, and router into
  labels/structured metadata, making the request filterable in Grafana without
  full-text search
