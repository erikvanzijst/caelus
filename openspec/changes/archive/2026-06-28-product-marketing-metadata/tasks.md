## 1. Model and schemas

- [x] 1.1 Add `category` and `replaces` as optional
      string fields on `ProductBase` in `api/app/models/core.py` so they are
      inherited by `ProductORM`, `ProductCreate`, and `ProductRead`.
- [x] 1.2 Declare the two fields as nullable text columns on `ProductORM`
      (matching the existing nullable-field style on the model).
- [x] 1.3 Add the two fields to `ProductUpdate` (which does not extend
      `ProductBase`) as optional, preserving partial-update semantics.
- [x] 1.4 Confirm `ProductRead` / `ProductReadBase` serialize the new fields
      and that the icon-url derivation is unaffected.

## 2. Migration

- [x] 2.1 Generate a new Alembic revision under `api/alembic/versions/` that
      adds the two nullable text columns to the `product` table.
- [x] 2.2 Implement the downgrade to drop the two columns.
- [x] 2.3 Verify upgrade/downgrade run cleanly on both SQLite (test) and the
      Postgres-style migration path.

## 3. Service layer

- [x] 3.1 Confirm `create_product` in `api/app/services/products.py` persists
      the new fields via `ProductORM.model_validate(payload)` (extend if any
      field is not picked up).
- [x] 3.2 Extend `update_product` to copy each new field onto the ORM object
      when present in the `ProductUpdate` payload, mirroring the existing
      `name` / `description` handling.

## 4. CLI parity

- [x] 4.1 Add options for `category` and `replaces` to
      the `create-product` command in `api/app/cli.py`, passing them into
      `ProductCreate`.
- [x] 4.2 Add the same options to the `update-product` command, passing them
      into `ProductUpdate`.

## 5. Admin UI

- [x] 5.1 Add inputs for the two fields to the product create flow under
      `ui/src/components/`, submitting them in the create payload.
- [x] 5.2 Add editing of the two fields to the existing product edit flow,
      submitting them in the update payload.

## 6. Landing page

- [x] 6.1 Read `category` and `replaces` from the
      product API response in the landing page instead of the hardcoded `APPS`
      map, and render the one-sentence blurb from the product's existing
      `description` (the card already falls back to `product.description`).
      Plumbed `category`/`replaces` through the shared `ProductSummary` loader
      (`useLandingProducts.ts`).
- [x] 6.2 Implement graceful fallback: omit an element when its field is empty.
- [x] 6.3 Remove the moved marketing content (the hardcoded `blurb`, `category`,
      and `replaces`) from `ui/src/components/landing/landingTokens.ts`, keeping
      any presentational tokens (e.g. accent color, now exposed via the
      `accentForProduct` helper that replaces `appMetaByName`/`APPS`).
- [x] 6.4 Drop the `engine` field entirely (not migrated to the API): remove
      the `engine?` property from the `AppEntry` interface and the
      `engine: 'Tuwunel homeserver'` value in
      `ui/src/components/landing/landingTokens.ts`, and remove the
      `meta?.engine` rendering block in
      `ui/src/components/landing/AppShowcase.tsx`.
- [x] 6.5 Migrate the second consumer of the hardcoded `APPS` map,
      `PricingSection.tsx`, to read `category` / `replaces` from the API product
      (via the shared `ProductSummary`) and the accent via `accentForProduct`.
      (Discovered during implementation; required to remove the `APPS` map
      without breaking the pricing cards.)
- [x] 6.6 Change the Hero "constellation" (`Hero.tsx`) to list the distinct
      product categories (deduped, first-seen order) instead of product names —
      which the Apps and Pricing sections already list — each with a generic
      category icon from a small `categoryIcon` map in `landingTokens.ts`
      (case-insensitive, with a generic fallback for unknown/edited
      categories). Accent colors stay deterministic; no product identity is
      hardcoded.

## 7. Tests

- [x] 7.1 Add API tests (FastAPI `TestClient`) covering create, read, and
      partial update of the new fields, including the optional/empty case.
- [x] 7.2 Add CLI tests (`typer.testing.CliRunner`) for setting the fields via
      `create-product` and `update-product`.

## 8. Validation

- [x] 8.1 Run `openspec validate product-marketing-metadata --strict` and
      ensure it passes.
- [x] 8.2 Run the API and CLI test suites and ensure they pass.
