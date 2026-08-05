## MODIFIED Requirements

### Requirement: API exposes and accepts marketing metadata
The product API SHALL return the marketing metadata fields on the product read
schema (`ProductRead`) and SHALL accept them on the product create and update
schemas (`ProductCreate` / `ProductUpdate`). Update SHALL allow setting any
subset of the fields without disturbing the others, consistent with the
existing partial-update behavior for product fields. For curated products,
update SHALL be rejected by the service-layer write guard, because `category`
and `replaces` are sourced from the product's catalog file.

#### Scenario: Read returns marketing metadata
- **WHEN** a client fetches a product (`GET /api/products/{id}` or
  `GET /api/products`)
- **THEN** the response includes the product's `category` and `replaces` fields

#### Scenario: Create accepts marketing metadata
- **WHEN** an admin creates a product with marketing metadata in the payload
- **THEN** the created product is returned with those fields populated

#### Scenario: Update changes a subset of fields
- **WHEN** an admin updates a non-curated product, providing only `category`
- **THEN** the product's `category` is updated
- **AND** its other marketing-metadata fields are unchanged

#### Scenario: Update of a curated product is rejected
- **WHEN** an admin updates a curated product's `category` or `replaces`
- **THEN** the request SHALL be rejected with a validation error naming the
  product's catalog file

### Requirement: Admin UI edits marketing metadata
The admin product create and edit experience SHALL allow entering and editing
the `category` and `replaces` fields for non-curated products, so
administrators can manage product marketing copy without changing frontend
code. For curated products these inputs SHALL be read-only, and the catalog
file SHALL be identified as the place to change them.

#### Scenario: Admin sets marketing metadata when creating a product
- **WHEN** an admin fills in the marketing-metadata inputs while creating a
  product
- **THEN** the values are submitted to the API and saved on the product

#### Scenario: Admin edits marketing metadata on an existing product
- **WHEN** an admin edits the marketing-metadata inputs on an existing
  non-curated product
- **THEN** the changes are persisted via the product update API

#### Scenario: Curated product metadata is read-only
- **WHEN** an admin views the marketing-metadata inputs of a curated product
- **THEN** the inputs SHALL be read-only and SHALL name the product's catalog
  file
