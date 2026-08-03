## ADDED Requirements

### Requirement: Products carry a stable catalog slug
The `product` table SHALL gain a nullable `slug` text column, unique among
non-deleted products, that joins a product row to its catalog file. The slug
MUST be independent of the product's display name, so that renaming a product
does not orphan its catalog entry or cause a duplicate product to be created.

#### Scenario: Renaming a curated product preserves the catalog link
- **WHEN** a curated product's `name` changes in its catalog file while its
  `slug` is unchanged
- **THEN** the reconciler SHALL update the existing product row rather than
  creating a new product

#### Scenario: Slug uniqueness is enforced
- **WHEN** a slug is assigned that is already held by another non-deleted
  product
- **THEN** the operation SHALL be rejected

### Requirement: The curated flag marks catalog ownership
The `product` table SHALL gain a non-null boolean `curated` column defaulting
to false. A product with `curated = true` is owned by the catalog; a product
with `curated = false` retains today's database-authored behavior. The migration
introducing the column SHALL set `curated = false` for all existing products, so
that no product changes behavior until its catalog file is added.

#### Scenario: Existing products are unaffected by the migration
- **WHEN** the migration adding `curated` is applied to a database with
  existing products
- **THEN** every existing product SHALL have `curated = false` and remain fully
  editable

#### Scenario: Reconciliation sets the flag
- **WHEN** the reconciler applies a catalog file to a product
- **THEN** that product's `curated` SHALL be true

### Requirement: Curated products reject writes through every interface
The product and template services SHALL reject mutating operations on a curated
product, including product field updates, product deletion, template creation,
and template deletion. Changing `visibility` is exempt, since it is runtime
state the catalog does not declare. Because the guard is enforced in the service layer, it
SHALL apply identically to the REST API, the CLI, and the admin UI, keeping
those surfaces in lockstep. The rejection error SHALL name the catalog file the
operator must edit instead.

#### Scenario: REST update of a curated product is rejected
- **WHEN** a client sends a product update for a curated product
- **THEN** the request SHALL be rejected with a validation error naming the
  product's catalog file

#### Scenario: CLI update of a curated product is rejected
- **WHEN** an admin runs `update-product` against a curated product
- **THEN** the command SHALL fail with the same validation error as the REST
  API

#### Scenario: Template creation on a curated product is rejected
- **WHEN** a client or admin attempts to create a template for a curated
  product
- **THEN** the operation SHALL be rejected

#### Scenario: Non-curated products are unaffected
- **WHEN** an admin updates a product with `curated = false`
- **THEN** the update SHALL succeed exactly as it does today

#### Scenario: Visibility is exempt from the guard
- **WHEN** an admin changes only a curated product's `visibility`
- **THEN** the change SHALL be applied, because the catalog owns what a product
  is while the database owns whether it is currently offered

### Requirement: Break-glass writes are permitted and leave visible drift
The service layer SHALL provide an explicit force option that bypasses the
curated write guard for urgent operator intervention on modifying operations.
A template created through the forced path SHALL leave `catalog_commit` null,
so that hand-made rows remain distinguishable from catalog-produced rows. A
subsequent reconciliation SHALL re-assert the catalog and repoint the canonical
template, causing the drift to self-heal.

#### Scenario: Forced write succeeds
- **WHEN** an admin performs a product update with the force option against a
  curated product
- **THEN** the update SHALL be applied

#### Scenario: Force is a request parameter, not resource state
- **WHEN** the override is invoked over the REST API
- **THEN** it SHALL be supplied as a `force` query parameter defaulting to
  false, so that it is available on endpoints that carry no request body
- **AND** it SHALL NOT appear on the product create, update, or read schemas

#### Scenario: Forced writes are recorded
- **WHEN** a write succeeds through the force option
- **THEN** the event SHALL be logged with the acting user and the affected
  product

#### Scenario: Forced template is unstamped
- **WHEN** a template is created through the forced path
- **THEN** its `catalog_commit` SHALL be null

#### Scenario: Next rollout re-asserts the catalog
- **WHEN** the reconciler runs after a forced change that diverges from the
  catalog
- **THEN** it SHALL repoint `product.template_id` to the template matching the
  catalog spec

### Requirement: Deletion of a curated product or its templates is never forceable
The force option SHALL NOT bypass the write guard for deleting a curated
product or one of its templates; such a request SHALL be refused even when
force is supplied. Deletion is excluded because the override cannot achieve
what the operator intends: the next reconciliation resolves a curated product
by slug among non-deleted rows, so a force-deleted product is not found, is not
adopted, and is recreated under a new id while existing deployments continue to
reference templates belonging to the old row. A force-deleted template is
likewise reinserted when its spec still matches the catalog. The refusal
message SHALL direct the operator to remove the product's catalog file first.

#### Scenario: Force-deleting a curated product is refused
- **WHEN** an admin deletes a curated product with the force option
- **THEN** the request SHALL be refused
- **AND** the error SHALL direct the operator to remove the product's catalog
  file first

#### Scenario: Force-deleting a curated product's template is refused
- **WHEN** an admin deletes a template belonging to a curated product with the
  force option
- **THEN** the request SHALL be refused

#### Scenario: Deletion succeeds once the product is no longer curated
- **WHEN** a product's catalog file has been removed and rolled out, and an
  admin then deletes the product
- **THEN** the deletion SHALL succeed without requiring the force option

#### Scenario: Non-curated deletion is unaffected
- **WHEN** an admin deletes a product with `curated = false`
- **THEN** the deletion SHALL succeed exactly as it does today

### Requirement: Only the reconciler writes the curated flag and slug
The `curated` flag and `slug` SHALL be written exclusively by the reconciler,
derived from whether a catalog file declares that slug. No REST endpoint, CLI
command, or admin UI action SHALL set or clear them, including under the force
option, so that catalog file presence is the single source of truth for whether
a product is catalog-managed and no ordering conflict between the two can arise.

#### Scenario: Curation cannot be set out of band
- **WHEN** any caller attempts to set or clear `curated` or `slug` directly
- **THEN** the attempt SHALL be rejected

#### Scenario: Releasing a product is a catalog change
- **WHEN** an operator wants a product to stop being catalog-managed
- **THEN** the supported action SHALL be removing its catalog file, which the
  reconciler applies on the next rollout

### Requirement: Template rows record their originating catalog commit
The `product_template_version` table SHALL gain a nullable `catalog_commit`
text column. It SHALL be written only when the reconciler inserts a row and
SHALL NOT be read by application logic, participate in template matching, or be
required by any code path. A null value indicates the row was not produced by
the catalog.

#### Scenario: Hand-authored templates have no commit
- **WHEN** a template is created through the admin UI or the CLI
- **THEN** its `catalog_commit` SHALL be null

#### Scenario: Audit trail resolves to a commit
- **WHEN** an operator inspects a template row created by the reconciler
- **THEN** its `catalog_commit` SHALL identify the commit whose catalog
  produced it
