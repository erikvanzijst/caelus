# pod-log-aggregation Specification

## Purpose

Collect logs from every pod across the cluster into a searchable, filesystem-backed Loki store via a Promtail DaemonSet, including parsed Traefik access logs, so operators can query application and ingress logs centrally — and so the platform API can serve a tenant their own deployment's output, which makes the stream labels a contract rather than operator convenience.

## Requirements

### Requirement: Cluster-wide pod log collection

The system SHALL collect logs from all pods across all namespaces in the k3s
cluster and ship them to a central Loki store, deployed cluster-wide in the
`monitoring` namespace (not per caelus-env).

#### Scenario: Logs from a new pod become available

- **WHEN** a pod in any namespace writes to stdout/stderr
- **THEN** a Promtail DaemonSet running on that pod's node reads the container
  log file and pushes the entries to Loki within seconds

### Requirement: Logs are labeled for querying

The system SHALL label every collected log stream with the Kubernetes metadata needed to select
one workload's output, and SHALL treat that label set as a contract rather than as an incidental
consequence of a shared relabel configuration.

A stream SHALL carry the `namespace`, `app`, `pod` and `container` labels derived from
Kubernetes pod metadata, as before.

A stream SHALL additionally carry the `instance` label derived from
`app.kubernetes.io/instance`, which for a tenant workload is the Helm release name and
identifies one deployment.

A stream SHALL additionally carry a `release_id` label derived from the `caelus.dev/release-id`
pod label, identifying the individual rollout that produced the pod. It SHALL be a stream label
and SHALL NOT be carried as structured metadata: `pod` is already a stream label and the release
identifier is constant within a pod, so the label creates no additional streams.

These labels are now depended upon by a user-facing reader, not only by operators in Grafana.
Changing or removing `namespace`, `instance` or `release_id` SHALL be understood to break
`deployment-log-api`.

#### Scenario: Logs are labeled for querying

- **WHEN** the collector forwards a log line to the store
- **THEN** the stream carries the `namespace`, `app`, `pod` and `container` labels derived from
  Kubernetes pod metadata

#### Scenario: One deployment's output is selectable

- **WHEN** a query selects on `namespace` and `instance` together
- **THEN** exactly one deployment's output is returned, across all of its releases

#### Scenario: One rollout's output is selectable

- **WHEN** a query additionally selects on `release_id`
- **THEN** only that rollout's output is returned, even where pods of two rollouts wrote
  concurrently

#### Scenario: A pod without a release label

- **WHEN** a pod that carries no `caelus.dev/release-id` label writes a line, as every platform
  and system pod does
- **THEN** the line is collected and labeled as before, with no `release_id` label and no error

### Requirement: Searchable log store

The system SHALL run Loki in single-binary mode with filesystem-backed persistent storage,
serving queries to Grafana and to the platform API.

The store SHALL enforce a bounded retention period, so that ingested volume cannot grow until
the persistent volume is exhausted. Retention SHALL be actively enforced by a running compactor
rather than assumed; a configured retention period with no component applying it is not
retention.

The retention period is an operational setting and SHALL NOT be presented to users as a promise
about how far back their logs reach.

#### Scenario: Operator searches logs in Grafana

- **WHEN** an operator queries a LogQL expression against the Loki datasource in Grafana
- **THEN** matching log lines from the selected namespace/app/pod are returned

#### Scenario: Logs survive a Loki pod restart

- **WHEN** the Loki pod is restarted or rescheduled
- **THEN** previously ingested logs remain available because the store is backed by a persistent
  volume

#### Scenario: Old logs are reclaimed

- **WHEN** log data ages past the configured retention period
- **THEN** it is deleted from the store and its space reclaimed, without operator intervention

### Requirement: Parsed Traefik access logs

The system SHALL parse Traefik access logs (Common Log Format) so ingress
requests are queryable by structured fields rather than raw text.

#### Scenario: Ingress request is queryable by status and route

- **WHEN** Traefik emits an access-log line for an incoming request
- **THEN** Promtail extracts fields such as HTTP method, status, and router into
  labels/structured metadata, making the request filterable in Grafana without
  full-text search
