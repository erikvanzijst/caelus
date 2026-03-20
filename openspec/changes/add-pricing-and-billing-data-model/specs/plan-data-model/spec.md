# plan-data-model Specification

## Purpose

Define the Plan and PlanTemplateVersion database models that represent
pricing tiers and their versioned commercial terms, mirroring the existing
Product/ProductTemplateVersion pattern.

## ADDED Requirements

### Requirement: Plan belongs to a product

The system SHALL store plans in a `plan` table. Each plan SHALL belong to
exactly one product via a `product_id` foreign key. A product MAY have
zero or more plans.

#### Scenario: Create a plan for a product
- **GIVEN** a product with id 1 exists
- **WHEN** a plan is created with `product_id=1` and `name="Basic 50GB"`
- **THEN** the plan is persisted with the given product_id and name
- **AND** the plan has an auto-generated `id` and `created_at`

#### Scenario: Multiple plans per product
- **GIVEN** a product with id 1 exists
- **WHEN** three plans are created for product 1 with names "Free", "Basic", and "Pro"
- **THEN** all three plans exist and `product_id=1` for each

#### Scenario: Plan references a nonexistent product
- **WHEN** a plan is created with a `product_id` that does not exist
- **THEN** the database rejects the insert with a foreign key violation

### Requirement: Plan name is unique per product (excluding soft-deleted)

The system SHALL enforce a partial unique index on `(product_id, lower(name))`
where `deleted_at IS NULL`. This prevents two active plans for the same
product from having the same name (case-insensitive), while allowing
soft-deleted plans to coexist with active plans of the same name.

#### Scenario: Duplicate plan name for same product
- **GIVEN** product 1 has an active plan named "Basic"
- **WHEN** another plan is created for product 1 with name "basic"
- **THEN** the database rejects the insert with a unique constraint violation

#### Scenario: Duplicate name allowed across products
- **GIVEN** product 1 has an active plan named "Basic"
- **WHEN** a plan is created for product 2 with name "Basic"
- **THEN** the plan is created successfully

#### Scenario: Reuse name after soft delete
- **GIVEN** product 1 has a soft-deleted plan named "Basic"
- **WHEN** a new plan is created for product 1 with name "Basic"
- **THEN** the plan is created successfully

### Requirement: Plan has a canonical template version

The system SHALL store a `template_id` foreign key on the plan record
that points to the plan's canonical (current) `PlanTemplateVersion`. This
FK MAY be NULL when the plan is first created before any template version
exists. The canonical template determines the commercial terms that new
subscribers see.

#### Scenario: Plan with canonical template
- **GIVEN** a plan exists with `template_id=5`
- **WHEN** the plan is queried
- **THEN** the canonical template version (id=5) is accessible via the
  plan's `template` relationship

#### Scenario: Update canonical template
- **GIVEN** a plan exists with `template_id=5`
- **AND** a new plan template version (id=6) is created for the same plan
- **WHEN** the plan's `template_id` is updated to 6
- **THEN** new queries for the plan's canonical template return version 6
- **AND** existing subscriptions that reference template version 5 are
  NOT affected

#### Scenario: Plan with no canonical template
- **WHEN** a plan is created without a `template_id`
- **THEN** the plan is created with `template_id=NULL`

### Requirement: Plan supports soft delete

The system SHALL support soft deletion of plans via a `deleted_at` nullable
timestamp column. Soft-deleted plans SHALL be excluded from default list
queries but SHALL remain in the database for referential integrity.

#### Scenario: Soft delete a plan
- **GIVEN** a plan with id 1 exists and `deleted_at IS NULL`
- **WHEN** the plan is soft-deleted
- **THEN** `deleted_at` is set to the current UTC timestamp
- **AND** the plan no longer appears in default list queries

#### Scenario: Soft-deleted plan still referenced by subscriptions
- **GIVEN** a plan has been soft-deleted
- **AND** subscriptions exist that reference template versions of that plan
- **THEN** the subscriptions remain valid and queryable

### Requirement: Plan name is mutable

The system SHALL allow the plan's `name` field to be updated after
creation. The plan name is a display label and is not part of the
commercial contract frozen by subscriptions.

#### Scenario: Rename a plan
- **GIVEN** a plan with name "Basic 50GB"
- **WHEN** the name is updated to "Starter 50GB"
- **THEN** the plan's name is "Starter 50GB"
- **AND** existing subscriptions to this plan's template versions are
  NOT affected

### Requirement: PlanTemplateVersion stores immutable commercial terms

The system SHALL store plan template versions in a `plan_template_version`
table. Each template version belongs to exactly one plan via a `plan_id`
foreign key. Template versions are immutable by convention -- once created,
their commercial fields (price_cents, billing_interval, storage_bytes,
description) SHALL NOT be modified.

#### Scenario: Create a plan template version
- **WHEN** a plan template version is created with `plan_id=1`,
  `price_cents=999`, `billing_interval='monthly'`, `storage_bytes=53687091200`
- **THEN** the template version is persisted with all given values
- **AND** it has an auto-generated `id` and `created_at`

#### Scenario: Template version fields
- **WHEN** a plan template version is created
- **THEN** it SHALL have the following fields:
  - `id` (primary key, auto-generated)
  - `plan_id` (FK to plan, NOT NULL)
  - `price_cents` (integer, NOT NULL) -- price in cents to avoid
    floating-point rounding
  - `billing_interval` (string, NOT NULL) -- 'monthly' or 'annual'
  - `storage_bytes` (integer, nullable) -- storage quota in bytes
  - `description` (string, nullable) -- marketing copy
  - `created_at` (datetime, auto-set)
  - `deleted_at` (datetime, nullable -- for soft delete)

### Requirement: Free plans are indicated by price

A plan template version with `price_cents = 0` represents a free plan.
There is no separate `is_free` flag or `plan_type` enum. The frontend
SHALL use this value to determine whether to show a payment flow.

#### Scenario: Free plan detection
- **GIVEN** a plan template version with `price_cents=0`
- **WHEN** the frontend evaluates whether to show a payment flow
- **THEN** no payment flow is shown

#### Scenario: Paid plan detection
- **GIVEN** a plan template version with `price_cents=999`
- **WHEN** the frontend evaluates whether to show a payment flow
- **THEN** the payment flow is shown

### Requirement: Billing interval values

The `billing_interval` field SHALL accept exactly two values: `monthly`
and `annual`. If a product offers both monthly and annual billing, these
SHALL be modeled as two separate Plan records.

#### Scenario: Monthly plan
- **WHEN** a plan template version is created with `billing_interval='monthly'`
- **THEN** the template version is persisted successfully

#### Scenario: Annual plan
- **WHEN** a plan template version is created with `billing_interval='annual'`
- **THEN** the template version is persisted successfully

#### Scenario: Invalid billing interval
- **WHEN** a plan template version is created with `billing_interval='weekly'`
- **THEN** the system rejects the input with a validation error

### Requirement: PlanTemplateVersion supports soft delete

The system SHALL support soft deletion of plan template versions via a
`deleted_at` nullable timestamp column. However, a plan template version
that is referenced by any subscription SHALL NOT be hard-deleted. Soft
delete is used for administrative removal of template versions that were
created in error and have no subscriptions.

#### Scenario: Soft delete an unreferenced template version
- **GIVEN** a plan template version with no subscriptions
- **WHEN** it is soft-deleted
- **THEN** `deleted_at` is set and it no longer appears in default queries

#### Scenario: Template version referenced by subscriptions
- **GIVEN** a plan template version that is referenced by subscriptions
- **WHEN** it is soft-deleted
- **THEN** existing subscriptions remain valid and can still access the
  template version's commercial terms

### Requirement: Price change workflow preserves existing subscriptions

When the commercial terms of a plan need to change (e.g. a price increase),
the admin SHALL create a new PlanTemplateVersion with the new terms and
update the plan's canonical `template_id`. Existing subscriptions that
reference the old template version SHALL NOT be affected. The old template
version remains in the database as an immutable historical record.

This is a critical business requirement: once a subscription has been sold
to a user at a particular price, that price commitment is honored
regardless of subsequent plan changes.

#### Scenario: Price increase does not affect existing subscribers
- **GIVEN** plan "Pro" has canonical template version 5 (price_cents=999)
- **AND** user A has an active subscription to template version 5
- **WHEN** admin creates template version 6 (price_cents=1499) for plan "Pro"
- **AND** admin updates plan "Pro" canonical template_id to 6
- **THEN** user A's subscription still references template version 5
- **AND** user A's effective price is still 999 cents
- **AND** new subscribers to plan "Pro" are offered template version 6
  at 1499 cents
