## ADDED Requirements

### Requirement: Product model stores marketing metadata
The product model (`ProductORM`) SHALL store the following nullable marketing
metadata fields, each persisted as a nullable text column on the `product`
table:

- `category`: the product's category (e.g. "Photos & video", "Messaging",
  "Passwords & passkeys").
- `replaces`: the proprietary services the product replaces (e.g.
  "Google Photos · iCloud Photos", "Slack · Microsoft Teams").
- `tagline`: a one-sentence marketing blurb describing the product.
- `engine`: an optional note for when the running software differs from the
  brand name (e.g. Matrix → "Tuwunel homeserver").

All four fields SHALL be optional; a product with none of them set is valid.
Purely presentational tokens (such as a per-product accent color) are NOT
product data and SHALL NOT be stored on the model.

#### Scenario: Product persists marketing metadata
- **WHEN** a product is created or updated with `category`, `replaces`,
  `tagline`, and `engine` values
- **THEN** those values are persisted on the `product` row and returned on
  subsequent reads of that product

#### Scenario: Marketing metadata is optional
- **WHEN** a product is created without any marketing metadata
- **THEN** the product is created successfully and its `category`, `replaces`,
  `tagline`, and `engine` fields are null

### Requirement: Database migration adds marketing metadata columns
An Alembic migration SHALL add the four nullable text columns (`category`,
`replaces`, `tagline`, `engine`) to the `product` table, and SHALL provide a
downgrade that removes them. Existing product rows SHALL remain valid after the
migration with the new columns set to null.

#### Scenario: Upgrade adds columns to existing data
- **WHEN** the migration is applied to a database containing existing products
- **THEN** the four new columns exist on the `product` table
- **AND** existing product rows are preserved with the new columns null

#### Scenario: Downgrade removes the columns
- **WHEN** the migration is downgraded
- **THEN** the four marketing-metadata columns are removed from the `product`
  table

### Requirement: API exposes and accepts marketing metadata
The product API SHALL return the marketing metadata fields on the product read
schema (`ProductRead`) and SHALL accept them on the product create and update
schemas (`ProductCreate` / `ProductUpdate`). Update SHALL allow setting any
subset of the fields without disturbing the others, consistent with the
existing partial-update behavior for product fields.

#### Scenario: Read returns marketing metadata
- **WHEN** a client fetches a product (`GET /api/products/{id}` or
  `GET /api/products`)
- **THEN** the response includes the product's `category`, `replaces`,
  `tagline`, and `engine` fields

#### Scenario: Create accepts marketing metadata
- **WHEN** an admin creates a product with marketing metadata in the payload
- **THEN** the created product is returned with those fields populated

#### Scenario: Update changes a subset of fields
- **WHEN** an admin updates a product, providing only `tagline`
- **THEN** the product's `tagline` is updated
- **AND** its other marketing-metadata fields are unchanged

### Requirement: CLI manages marketing metadata at parity with the API
The CLI SHALL be able to set the marketing metadata fields when creating a
product and when updating a product, providing the same capability as the REST
API so the two remain in lockstep.

#### Scenario: CLI creates a product with marketing metadata
- **WHEN** an admin runs the `create-product` command with options for
  `category`, `replaces`, `tagline`, and `engine`
- **THEN** the created product carries those values

#### Scenario: CLI updates marketing metadata
- **WHEN** an admin runs the `update-product` command with one or more
  marketing-metadata options
- **THEN** the specified fields are updated and the others are left unchanged

### Requirement: Admin UI edits marketing metadata
The admin product create and edit experience SHALL allow entering and editing
the `category`, `replaces`, `tagline`, and `engine` fields, so administrators
can manage product marketing copy without changing frontend code.

#### Scenario: Admin sets marketing metadata when creating a product
- **WHEN** an admin fills in the marketing-metadata inputs while creating a
  product
- **THEN** the values are submitted to the API and saved on the product

#### Scenario: Admin edits marketing metadata on an existing product
- **WHEN** an admin edits the marketing-metadata inputs on an existing product
- **THEN** the changes are persisted via the product update API

### Requirement: Landing page renders marketing metadata from the API
The anonymous landing page SHALL render each product's `category`, `replaces`,
`tagline`, and `engine` from the product API instead of the hardcoded `APPS`
map in `landingTokens.ts`. When a field is empty, the landing page SHALL
gracefully omit the corresponding element rather than render a placeholder or
break. The hardcoded marketing content for these fields SHALL be removed once
the page reads them from the API; non-product presentational tokens (such as
accent color) MAY remain in the UI.

#### Scenario: Landing page shows API-provided metadata
- **WHEN** the landing page renders a product whose API record has
  `category`, `replaces`, `tagline`, and `engine`
- **THEN** the page displays those values for that product

#### Scenario: Graceful fallback for empty fields
- **WHEN** the landing page renders a product whose `engine` (or any other
  marketing field) is empty
- **THEN** the page omits that element and renders the rest of the product
  without error
