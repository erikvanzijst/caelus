## 1. Model and schemas

- [ ] 1.1 Add `category`, `replaces`, `tagline`, and `engine` as optional
      string fields on `ProductBase` in `api/app/models/core.py` so they are
      inherited by `ProductORM`, `ProductCreate`, and `ProductRead`.
- [ ] 1.2 Declare the four fields as nullable text columns on `ProductORM`
      (matching the existing nullable-field style on the model).
- [ ] 1.3 Add the four fields to `ProductUpdate` (which does not extend
      `ProductBase`) as optional, preserving partial-update semantics.
- [ ] 1.4 Confirm `ProductRead` / `ProductReadBase` serialize the new fields
      and that the icon-url derivation is unaffected.

## 2. Migration

- [ ] 2.1 Generate a new Alembic revision under `api/alembic/versions/` that
      adds the four nullable text columns to the `product` table.
- [ ] 2.2 Implement the downgrade to drop the four columns.
- [ ] 2.3 Verify upgrade/downgrade run cleanly on both SQLite (test) and the
      Postgres-style migration path.

## 3. Service layer

- [ ] 3.1 Confirm `create_product` in `api/app/services/products.py` persists
      the new fields via `ProductORM.model_validate(payload)` (extend if any
      field is not picked up).
- [ ] 3.2 Extend `update_product` to copy each new field onto the ORM object
      when present in the `ProductUpdate` payload, mirroring the existing
      `name` / `description` handling.

## 4. CLI parity

- [ ] 4.1 Add options for `category`, `replaces`, `tagline`, and `engine` to
      the `create-product` command in `api/app/cli.py`, passing them into
      `ProductCreate`.
- [ ] 4.2 Add the same options to the `update-product` command, passing them
      into `ProductUpdate`.

## 5. Admin UI

- [ ] 5.1 Add inputs for the four fields to the product create flow under
      `ui/src/components/`, submitting them in the create payload.
- [ ] 5.2 Add editing of the four fields to the existing product edit flow,
      submitting them in the update payload.

## 6. Landing page

- [ ] 6.1 Read `category`, `replaces`, `tagline`, and `engine` from the
      product API response in the landing page instead of the hardcoded `APPS`
      map.
- [ ] 6.2 Implement graceful fallback: omit an element when its field is empty.
- [ ] 6.3 Remove the moved marketing content from
      `ui/src/components/landing/landingTokens.ts`, keeping any presentational
      tokens (e.g. accent color).

## 7. Tests

- [ ] 7.1 Add API tests (FastAPI `TestClient`) covering create, read, and
      partial update of the new fields, including the optional/empty case.
- [ ] 7.2 Add CLI tests (`typer.testing.CliRunner`) for setting the fields via
      `create-product` and `update-product`.

## 8. Validation

- [ ] 8.1 Run `openspec validate product-marketing-metadata --strict` and
      ensure it passes.
- [ ] 8.2 Run the API and CLI test suites and ensure they pass.
