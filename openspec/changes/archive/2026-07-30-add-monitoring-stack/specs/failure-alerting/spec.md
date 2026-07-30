## ADDED Requirements

### Requirement: Failure alert rules

The system SHALL evaluate Prometheus alert rules that fire when workloads or
nodes are failing, covering at minimum crash-looping pods, unreachable nodes,
high node memory usage, and failed cronjobs.

#### Scenario: Crash-looping pod raises an alert

- **WHEN** a pod container has been in `CrashLoopBackOff` for longer than the
  rule's `for` window
- **THEN** the `PodCrashLooping` alert enters firing state with the pod and
  namespace in its labels/annotations

#### Scenario: Unreachable node raises an alert

- **WHEN** a node's node-exporter target is down (`up == 0`) beyond the `for`
  window
- **THEN** the `NodeDown` alert fires with a critical severity

#### Scenario: High memory usage raises an alert

- **WHEN** a node's used memory exceeds the configured threshold for the `for`
  window
- **THEN** the `HighMemoryUsage` alert fires with a warning severity

#### Scenario: Failed cronjob raises an alert

- **WHEN** the most recent run of a non-suspended cronjob failed with no later
  successful run
- **THEN** the `CronJobFailed` alert fires identifying the cronjob and namespace

### Requirement: Email delivery via in-cluster relay

The system SHALL deliver alert notifications by email through the existing
in-cluster mailer relay, without duplicating external SMTP credentials into the
monitoring configuration.

#### Scenario: Firing alert is emailed

- **WHEN** an alert transitions to firing
- **THEN** Alertmanager sends an email to the configured recipient
  (`alert_email_to`) via `smtp.mailer.svc.cluster.local:25` (no auth, no TLS to
  the relay)

#### Scenario: No external SMTP secrets in the monitoring module

- **WHEN** the monitoring stack is configured
- **THEN** it references the in-cluster relay only and does not require external
  SMTP host/username/password variables of its own

### Requirement: Alertmanager is not publicly exposed

The system SHALL keep Alertmanager reachable only as a ClusterIP service, not
exposed via ingress.

#### Scenario: Operator reaches Alertmanager privately

- **WHEN** an operator needs the Alertmanager UI
- **THEN** access is available only via `kubectl port-forward` with no public
  ingress route
