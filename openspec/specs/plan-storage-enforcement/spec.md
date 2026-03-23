# plan-storage-enforcement Specification

## Purpose

Define how the reconciler projects plan-level storage quotas into Helm
values so that each product chart can enforce PVC size limits based on
the subscriber's plan — without coupling the reconciler to any specific
chart structure.

## Overview

Plans define a `storage_bytes` field on `PlanTemplateVersion`. During
reconciliation, the reconciler reads the deployment's subscription plan
template and injects a well-known `caelus.plan` namespace into the Helm
values as a system override (highest merge precedence). Each product
chart decides whether and how to consume these values.

```
PlanTemplateVersion.storage_bytes
        │
        ▼
  Reconciler._build_merged_values()
        │  reads deployment.subscription.plan_template.storage_bytes
        │  converts to Kubernetes size string
        │  injects as system_overrides: {"caelus": {"plan": {...}}}
        ▼
  merge_values_scoped(defaults, user_delta, system_overrides)
        │  system_overrides wins over user_delta and defaults
        ▼
  Helm values passed to `helm upgrade --install`
        │
        ▼
  Chart template references .Values.caelus.plan.storageSize
        │  e.g. {{ .Values.caelus.plan.storageSize | default "100Gi" }}
        ▼
  PVC created with plan-enforced size
```

## ADDED Requirements

### Requirement: Reconciler injects plan metadata as system overrides

The reconciler SHALL read `storage_bytes` from the deployment's
subscription plan template and inject it into the Helm values under
the reserved `caelus.plan` namespace. This injection MUST use the
`system_overrides` parameter of `merge_values_scoped`, which has the
highest merge precedence, ensuring that user-supplied values cannot
override plan limits.

#### Scenario: Deployment with a plan that defines storage_bytes
- **GIVEN** a deployment with an active subscription
- **AND** the subscription's plan template has `storage_bytes=10737418240` (10 GiB)
- **WHEN** the reconciler builds merged values
- **THEN** the merged values include `caelus.plan.storageBytes` set to `10737418240`
- **AND** the merged values include `caelus.plan.storageSize` set to `"10Gi"`
- **AND** user-supplied values at any path are preserved
- **AND** user-supplied values under `caelus.plan` are overridden by the system values

#### Scenario: Deployment with a plan that has null storage_bytes
- **GIVEN** a deployment with an active subscription
- **AND** the subscription's plan template has `storage_bytes=None`
- **WHEN** the reconciler builds merged values
- **THEN** the merged values include `caelus.plan` as an empty object
- **AND** charts fall back to their own default storage sizes via `| default`

#### Scenario: Deployment with a plan that has zero storage_bytes
- **GIVEN** a deployment with an active subscription
- **AND** the subscription's plan template has `storage_bytes=0`
- **WHEN** the reconciler builds merged values
- **THEN** the merged values include `caelus.plan` as an empty object
- **AND** charts fall back to their own default storage sizes via `| default`

#### Scenario: Deployment with no subscription
- **GIVEN** a deployment with `subscription_id=NULL`
- **WHEN** the reconciler builds merged values
- **THEN** the merged values do NOT contain a `caelus` key
- **AND** chart templates that reference `.Values.caelus.plan` will fail
  with a nil map traversal error, surfacing the missing subscription

### Requirement: bytes_to_k8s_size conversion

The system SHALL provide a `bytes_to_k8s_size` function that converts
an integer byte count to the largest clean Kubernetes binary size unit
(Ti, Gi, Mi, Ki). If the value does not divide evenly into any binary
unit, the raw byte count SHALL be returned as a string.

#### Scenario: Value divisible by GiB
- **WHEN** `bytes_to_k8s_size(10737418240)` is called
- **THEN** the result is `"10Gi"`

#### Scenario: Value divisible by MiB but not GiB
- **WHEN** `bytes_to_k8s_size(536870912)` is called
- **THEN** the result is `"512Mi"`

#### Scenario: Value divisible by TiB
- **WHEN** `bytes_to_k8s_size(1099511627776)` is called
- **THEN** the result is `"1Ti"`

#### Scenario: Value not divisible by any binary unit
- **WHEN** `bytes_to_k8s_size(500000000)` is called
- **THEN** the result is `"500000000"`

#### Scenario: Zero bytes
- **WHEN** `bytes_to_k8s_size(0)` is called
- **THEN** the result is `"0"`

### Requirement: Plan values use highest merge precedence

Plan-derived values injected under `caelus.plan` MUST be passed as
`system_overrides` to `merge_values_scoped`. This guarantees that even
if a user injects `caelus.plan.storageSize` in their `user_values_json`,
the plan-enforced value wins.

#### Scenario: User attempts to override plan storage via user_values_json
- **GIVEN** a deployment whose plan template has `storage_bytes=10737418240`
- **AND** the deployment's `user_values_json` contains `{"caelus": {"plan": {"storageSize": "999Ti"}}}`
- **WHEN** the reconciler builds merged values
- **THEN** `caelus.plan.storageSize` in the final values is `"10Gi"` (from the plan)
- **AND** the user's attempted override is discarded

### Requirement: Chart templates consume plan values with fallback defaults

Product Helm charts that use storage SHALL reference
`.Values.caelus.plan.storageSize` in their PVC templates with a
`| default` fallback to the chart's own default size:

```
{{ .Values.caelus.plan.storageSize | default <chart-default> }}
```

The reconciler guarantees that `caelus.plan` is always present
when a deployment has a subscription (even if empty). If
`caelus.plan` is unexpectedly absent (no subscription, or a
reconciler bug), Go template map traversal will fail loudly —
this is the intended behavior, as it surfaces the problem rather
than silently applying an arbitrary default.

Charts that do not use storage MAY ignore the `caelus.plan`
namespace entirely — but the `caelus` key will still be present
in values.

#### Scenario: Chart renders PVC with plan storage size
- **GIVEN** Helm values contain `caelus.plan.storageSize: "10Gi"`
- **WHEN** the PVC template is rendered
- **THEN** the PVC's `resources.requests.storage` is `10Gi`

#### Scenario: Chart renders PVC without plan values
- **GIVEN** Helm values do NOT contain `caelus.plan`
- **WHEN** the PVC template is rendered
- **THEN** the PVC's `resources.requests.storage` falls back to the chart's default (e.g. `100Gi`)
- **AND** template rendering does NOT fail with a nil map traversal error

### Requirement: Chart values schema permits optional caelus namespace

Product Helm charts that define a `values.schema.json` with
`additionalProperties: false` MUST include `caelus` as an optional
property so that Helm schema validation does not reject plan-injected
values. The `caelus` object and its contents SHALL NOT be marked as
required.

#### Scenario: Helm install with caelus values passes schema validation
- **GIVEN** a chart with `values.schema.json` that includes `caelus` as optional
- **WHEN** Helm installs with values containing `caelus.plan.storageSize`
- **THEN** schema validation passes

#### Scenario: Helm install without caelus values passes schema validation
- **GIVEN** a chart with `values.schema.json` that includes `caelus` as optional
- **WHEN** Helm installs with values that do NOT contain `caelus`
- **THEN** schema validation passes
