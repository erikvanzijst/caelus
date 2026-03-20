# plan-api Specification

## Purpose

Define the RESTful API endpoints and CLI commands for browsing, creating,
and managing plans and plan template versions.

## ADDED Requirements

### Requirement: List plans for a product

The system SHALL provide a `GET /products/{product_id}/plans` endpoint that
returns all non-deleted plans for the given product. Each plan in the
response SHALL include its canonical template version details (price,
billing interval, storage, description). The endpoint follows the existing
nested-route convention (`/products/{id}/templates`).

#### Scenario: List plans for a product with plans
- **GIVEN** product 1 has two active plans: "Free" and "Pro"
- **WHEN** `GET /products/1/plans` is called
- **THEN** the response contains two plan objects
- **AND** each plan includes its canonical template version details

#### Scenario: List plans for a product with no plans
- **GIVEN** product 2 has no plans
- **WHEN** `GET /products/2/plans` is called
- **THEN** the response contains an empty list

#### Scenario: Soft-deleted plans are excluded
- **GIVEN** product 1 has plans "Free" (active) and "Legacy" (soft-deleted)
- **WHEN** `GET /products/1/plans` is called
- **THEN** the response contains only the "Free" plan

#### Scenario: List plans for nonexistent product
- **WHEN** `GET /products/999/plans` is called
- **THEN** the response is 404

### Requirement: Get a single plan

The system SHALL provide a `GET /plans/{plan_id}` endpoint that returns a
single plan with its canonical template version details.

#### Scenario: Get an existing plan
- **GIVEN** plan 1 exists with canonical template version 5
- **WHEN** `GET /plans/1` is called
- **THEN** the response contains the plan with template version 5 details

#### Scenario: Get a soft-deleted plan
- **GIVEN** plan 1 has been soft-deleted
- **WHEN** `GET /plans/1` is called
- **THEN** the response is 404

#### Scenario: Get a nonexistent plan
- **WHEN** `GET /plans/999` is called
- **THEN** the response is 404

### Requirement: Create a plan (admin only)

The system SHALL provide a `POST /products/{product_id}/plans` endpoint
(admin only) that creates a new plan for the given product. The request
body SHALL include `name` (required). The response SHALL be the created
plan resource.

#### Scenario: Admin creates a plan
- **GIVEN** the request is from an admin user
- **AND** product 1 exists
- **WHEN** `POST /products/1/plans` is called with `{"name": "Pro 500GB"}`
- **THEN** a plan is created with `product_id=1`, `name="Pro 500GB"`
- **AND** `template_id` is NULL (no template yet)
- **AND** the response is 201 with the created plan

#### Scenario: Non-admin cannot create a plan
- **GIVEN** the request is from a non-admin user
- **WHEN** `POST /products/1/plans` is called
- **THEN** the response is 403

#### Scenario: Create plan for nonexistent product
- **GIVEN** the request is from an admin user
- **WHEN** `POST /products/999/plans` is called
- **THEN** the response is 404

#### Scenario: Duplicate plan name
- **GIVEN** product 1 has an active plan named "Pro"
- **WHEN** `POST /products/1/plans` is called with `{"name": "Pro"}`
- **THEN** the response is 409 (conflict)

### Requirement: Update a plan (admin only)

The system SHALL provide a `PATCH /plans/{plan_id}` endpoint (admin only)
that updates a plan's mutable fields. Updatable fields: `name`,
`template_id` (to change the canonical template version).

#### Scenario: Rename a plan
- **GIVEN** plan 1 has name "Basic"
- **WHEN** `PATCH /plans/1` is called with `{"name": "Starter"}`
- **THEN** the plan's name is updated to "Starter"

#### Scenario: Update canonical template
- **GIVEN** plan 1 has `template_id=5`
- **AND** a new template version 6 exists for plan 1
- **WHEN** `PATCH /plans/1` is called with `{"template_id": 6}`
- **THEN** the plan's canonical template is updated to version 6

#### Scenario: Update canonical template to a version from another plan
- **GIVEN** plan 1 exists
- **AND** template version 10 belongs to plan 2
- **WHEN** `PATCH /plans/1` is called with `{"template_id": 10}`
- **THEN** the response is 400 (template does not belong to this plan)

### Requirement: Delete a plan (admin only)

The system SHALL provide a `DELETE /plans/{plan_id}` endpoint (admin only)
that soft-deletes the plan by setting `deleted_at`.

#### Scenario: Soft-delete a plan
- **GIVEN** plan 1 exists and is active
- **WHEN** `DELETE /plans/1` is called by an admin
- **THEN** the plan's `deleted_at` is set
- **AND** subsequent `GET /plans/1` returns 404
- **AND** existing subscriptions to this plan's templates are NOT affected

### Requirement: Create a plan template version (admin only)

The system SHALL provide a `POST /plans/{plan_id}/templates` endpoint
(admin only) that creates a new template version for the given plan. The
request body SHALL include `price_cents` (required), `billing_interval`
(required), and optionally `storage_bytes`, `description`, and
`sort_order`. The response SHALL be the created template version resource.

#### Scenario: Create a template version
- **GIVEN** plan 1 exists
- **WHEN** `POST /plans/1/templates` is called with:
  ```
  {
    "price_cents": 999,
    "billing_interval": "monthly",
    "storage_bytes": 53687091200,
    "description": "50GB storage, billed monthly"
  }
  ```
- **THEN** a template version is created with the given values
- **AND** the response is 201

#### Scenario: Invalid billing interval
- **WHEN** `POST /plans/1/templates` is called with
  `{"price_cents": 999, "billing_interval": "weekly"}`
- **THEN** the response is 422 (validation error)

#### Scenario: Missing required fields
- **WHEN** `POST /plans/1/templates` is called with
  `{"description": "No price"}`
- **THEN** the response is 422 (validation error -- price_cents and
  billing_interval are required)

### Requirement: CLI parity for plan management

The CLI SHALL provide commands equivalent to all plan API endpoints:

- `plan list <product_id>` -- list plans for a product
- `plan create <product_id> --name <name>` -- create a plan (admin)
- `plan update <plan_id> [--name <name>] [--template-id <id>]` --
  update a plan (admin)
- `plan delete <plan_id>` -- soft-delete a plan (admin)
- `plan template create <plan_id> --price-cents <n>
  --billing-interval <interval> [--storage-bytes <n>]
  [--description <text>] [--sort-order <n>]` -- create a template
  version (admin)

#### Scenario: CLI list plans
- **WHEN** `plan list 1` is run
- **THEN** the output displays plans for product 1 in YAML format

#### Scenario: CLI create plan
- **WHEN** `plan create 1 --name "Pro"` is run by an admin
- **THEN** a plan is created for product 1
- **AND** the created plan is displayed in YAML format

#### Scenario: CLI create template version
- **WHEN** `plan template create 1 --price-cents 999
  --billing-interval monthly` is run
- **THEN** a template version is created for plan 1
