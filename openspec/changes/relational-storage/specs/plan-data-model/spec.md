## MODIFIED Requirements

### Requirement: PlanTemplateVersion stores immutable commercial terms

The system SHALL store plan template versions in a `plan_template_version`
table. Each template version belongs to exactly one plan via a `plan_id`
foreign key. Template versions are immutable by convention -- once created,
their commercial fields (price_cents, billing_interval, storage_bytes,
database_bytes) SHALL NOT be modified.

`storage_bytes` and `database_bytes` are separate allowances bounding separate
subsystems, and neither SHALL be derived from the other.

#### Scenario: Create a plan template version
- **WHEN** a plan template version is created with `plan_id=1`,
  `price_cents=999`, `billing_interval='monthly'`, `storage_bytes=53687091200`,
  `database_bytes=1073741824`
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
  - `storage_bytes` (integer, nullable) -- object storage quota in bytes
  - `database_bytes` (integer, nullable) -- relational database quota in bytes
  - `created_at` (datetime, auto-set)
  - `deleted_at` (datetime, nullable -- for soft delete)

#### Scenario: A plan bounds only the subsystems it declares
- **WHEN** a plan template version declares `storage_bytes` but no `database_bytes`
- **THEN** the object-storage allowance is available
- **AND** no relational database allowance can be resolved from it
