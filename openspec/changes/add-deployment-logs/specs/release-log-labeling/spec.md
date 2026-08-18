## Purpose

How a release identifier reaches an individual log line — supplied to the chart as a system value,
rendered onto the pod template and nowhere else, and relabeled into a stream label on the log
store — so that two pods writing concurrently during a rollout remain attributable to the release
each belongs to.

## ADDED Requirements

### Requirement: The release identifier is offered to every chart

The reconciler SHALL supply the release's `uuid4` to the chart on every apply, for every
product, without regard to whether that chart renders it. There SHALL be no per-product
condition on the platform side.

The identifier SHALL already exist and be persisted before the Helm operation begins, because the
release is created by the request that asked for the rollout. It SHALL NOT be derived from anything
observed after the fact.

Rendering the value SHALL be the chart's decision. A chart that renders it gains release
attribution for its pods; a chart that ignores it SHALL apply and run normally, and its
deployment's logs SHALL remain readable without release attribution.

Adopting the label in a chart that does not yet render it SHALL therefore be a chart-only
change, requiring no platform, reconciler or collector work.

#### Scenario: A chart that renders the value

- **WHEN** a release of a product whose chart renders the identifier is applied
- **THEN** its pods carry the release identifier

#### Scenario: A chart that ignores the value

- **WHEN** a release of a product whose chart does not render the identifier is applied
- **THEN** the apply succeeds and the pods carry no release label
- **AND** the deployment's logs remain readable without release attribution

### Requirement: A rendered identifier is stamped on every pod of its release

Where a chart renders the identifier, it SHALL do so as the `caelus.dev/release-id` label on the
pod template of the workload it creates, so that every pod of that release carries it.

A pod created later in the release's life — by a node eviction, a rescheduling or a kubelet
restart — SHALL carry the same identifier without any component having to observe its creation.

The label key SHALL follow the platform's existing convention for identifiers stamped on pods,
alongside `caelus.dev/build-id`, `caelus.dev/component` and `caelus.dev/tenant`.

#### Scenario: A rollout's pods are labeled

- **WHEN** a release is applied from a chart that renders the identifier
- **THEN** every pod created for it carries `caelus.dev/release-id` set to that release's
  identifier

#### Scenario: A pod is replaced without a new rollout

- **WHEN** a pod of the applied release is evicted and rescheduled, with no new release applied
- **THEN** the replacement pod carries the same release identifier as the pod it replaced

#### Scenario: An atomic rollback restores the earlier release

- **WHEN** a rollout fails and Helm rolls back
- **THEN** the pods that come back carry the **earlier** release's identifier, because they are
  that release's pods

### Requirement: The release label is applied to the pod template, never to a selector

The release identifier SHALL be rendered through a chart helper used **only** at the pod
template's metadata.

It SHALL NOT be added to any helper that feeds a workload's `spec.selector.matchLabels`, which
is immutable on a Kubernetes Deployment and would cause every subsequent apply to fail.

It SHALL NOT be added to any helper that feeds a Service's `spec.selector`, which would cause
the Service to select only the new release's pods before they are ready, and drop traffic during
a rollout.

#### Scenario: A second rollout is applied

- **WHEN** a deployment that already has a release is applied again with a new release
  identifier
- **THEN** the apply succeeds, because no immutable selector field changed

#### Scenario: Traffic during a rollout

- **WHEN** a new release's pods are starting while the previous release's pods still serve
- **THEN** the Service continues to select the serving pods throughout

### Requirement: The release identifier is a system value a tenant cannot forge

The release identifier SHALL be supplied to the chart as a system override under the platform's
reserved `caelus` values namespace, applied after user-scoped values so that user values cannot
shadow it.

A tenant SHALL NOT be able to set, override or influence the release identifier through user
values, the deployment form, or any request field.

#### Scenario: A tenant supplies a conflicting value

- **WHEN** a tenant submits user values that attempt to set the release identifier
- **THEN** the rendered pod carries the platform's identifier, not the tenant's

### Requirement: The release identifier is a Loki stream label

The log collector SHALL relabel the `caelus.dev/release-id` pod label into a Loki **stream
label**, so that a query for one release is an index lookup rather than a scan of every line the
deployment has produced.

It SHALL NOT be carried as structured metadata. The usual reason to prefer structured metadata —
avoiding stream multiplication from a high-cardinality field — does not apply, because `pod` is
already a stream label and the release identifier is constant within a pod. It is functionally
dependent on a label that already exists, so promoting it widens each existing series without
creating new ones.

#### Scenario: Logs are queryable by release

- **WHEN** a pod carrying a release identifier writes a line
- **THEN** the line is retrievable by a selector naming that release, without scanning the
  deployment's other releases

#### Scenario: Two releases write concurrently

- **WHEN** a rollout is in progress and pods of two releases are writing at the same time
- **THEN** a query naming one release returns only that release's lines, with no interleaving
  from the other

#### Scenario: A release's pods have been deleted

- **WHEN** a rollout failed, was rolled back, and its pods were deleted
- **THEN** that release's lines remain retrievable by its identifier

### Requirement: Every returned line is attributable to a release

A log line returned from the store SHALL carry the identifier of the release that produced it,
so that a reader following a deployment across a rollout can tell which release each line came
from without issuing a second query.

#### Scenario: A reader observes a rollover

- **WHEN** a reader is following a deployment and a new release becomes live
- **THEN** the lines from before and after the rollover are individually attributable to their
  respective releases
