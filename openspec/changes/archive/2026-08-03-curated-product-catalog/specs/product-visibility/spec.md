## ADDED Requirements

### Requirement: Products carry a visibility setting
The `product` table SHALL gain a non-null `visibility` column accepting the
values `public` and `admin`. `public` means the product is offered to end users
in the product catalog; `admin` means it is hidden from end users. Visibility
SHALL be independent of the `curated` flag, so that a product may be
catalog-managed yet hidden, or database-authored yet public.

#### Scenario: Curated and hidden
- **WHEN** a curated product declares `visibility: admin`
- **THEN** it SHALL remain reconciler-managed while being hidden from end users

#### Scenario: Deprecated product stays manageable
- **WHEN** a curated product is superseded and its visibility is set to `admin`
- **THEN** it SHALL continue to receive catalog updates without being offered
  to new users

### Requirement: End-user product listings filter on visibility
Product listings served to end users SHALL include only non-deleted products
whose `visibility` is `public`. Products with `visibility` of `admin` SHALL NOT
appear in end-user listings regardless of their `curated` value.

#### Scenario: Hidden product is excluded
- **WHEN** an end user requests the product list and a product has
  `visibility: admin`
- **THEN** that product SHALL NOT appear in the response

#### Scenario: Public products are listed
- **WHEN** an end user requests the product list
- **THEN** every non-deleted product with `visibility: public` SHALL appear,
  whether curated or not

### Requirement: Admin listings ignore visibility and curation
Administrative product listings SHALL return all non-deleted products, filtered
only by `deleted_at`. Admins SHALL see curated and non-curated products, and
public and admin-visibility products alike, so that experimental and deprecated
products remain discoverable to operators.

#### Scenario: Admin sees everything
- **WHEN** an admin requests the product list and the database contains
  curated, non-curated, public, and admin-visibility products
- **THEN** all non-deleted products SHALL be returned

#### Scenario: Deleted products remain excluded
- **WHEN** an admin requests the product list and a product is soft deleted
- **THEN** that product SHALL NOT be returned

### Requirement: Administrators can change the visibility of any product
Administrators SHALL be able to change any product's `visibility` through the
REST API, the CLI, and the admin UI, whether the product is curated or not, so
that a product can be published or withdrawn from the end-user catalog
immediately rather than waiting for a merge and a rollout. The curated write
guard SHALL NOT block a visibility change: the catalog owns what a product is,
while the database owns whether it is currently offered. The admin UI SHALL
present visibility as an explicit control in the product detail panel, showing
the product's current setting, and SHALL remain enabled for curated products
even where the rest of the panel is read-only.

#### Scenario: Admin publishes a product
- **WHEN** an admin changes a product's visibility from `admin` to `public`
- **THEN** the change SHALL be persisted
- **AND** the product SHALL subsequently appear in the end-user product list

#### Scenario: Admin withdraws a product
- **WHEN** an admin changes a product's visibility from `public` to `admin`
- **THEN** the product SHALL no longer appear in the end-user product list
- **AND** existing deployments of that product SHALL be unaffected

#### Scenario: Curated product visibility remains editable
- **WHEN** an admin changes a curated product's visibility
- **THEN** the change SHALL be applied without requiring the force option
- **AND** the control SHALL be enabled in the admin UI

#### Scenario: CLI changes visibility at parity with the API
- **WHEN** an admin runs `update-product` with a visibility option
- **THEN** the value SHALL be updated exactly as it is through the REST API

#### Scenario: Visibility changes are recorded
- **WHEN** a product's visibility changes
- **THEN** the event SHALL be logged with the acting user and the product

### Requirement: Existing products preserve current behavior on migration
The migration introducing `visibility` SHALL set `visibility = 'public'` for
all existing products, preserving today's behavior in which every product is
offered to end users. Newly created products SHALL default to `admin`, so that
a product being onboarded is not exposed to end users before it is ready.

#### Scenario: Migration backfills existing products
- **WHEN** the migration is applied to a database with existing products
- **THEN** every existing product SHALL have `visibility = 'public'`

#### Scenario: New product starts hidden
- **WHEN** an admin creates a new product without specifying visibility
- **THEN** its `visibility` SHALL be `admin`
