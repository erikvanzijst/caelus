## Why

The new anonymous landing page hardcodes per-product marketing copy (category,
"replaces", and a one-sentence blurb) in
`ui/src/components/landing/landingTokens.ts` as an `APPS` array matched to
products by name. This is brittle: editors must change frontend code to add or
edit a product's copy, and string-name matching silently breaks when a product
is renamed or a name does not line up. This metadata describes the product and
belongs with the product, so it should be stored on the product and served by
the API like the product's name, description, and icon already are.

## What Changes

- Add nullable marketing-metadata fields to the product model (`ProductORM`):
  `category` and `replaces`.
- Expose these fields on the product read schema (`ProductRead`) so the API
  returns them, and accept them on the create/update schemas
  (`ProductCreate` / `ProductUpdate`) so admins can set and edit them.
- Add an Alembic migration that adds the two nullable text columns to the
  `product` table.
- Extend the admin UI so these fields can be entered when creating a product
  and edited on an existing product.
- Update the landing page to read category / replaces from the product API
  instead of the hardcoded `APPS` map, and to render the one-sentence blurb
  from the product's existing `description` field where it currently uses the
  hardcoded blurb, with a graceful fallback (omit the element) when a field is
  empty.
- Do not introduce a separate `tagline` field: today it would merely duplicate
  the existing `description`, so the landing-page blurb is sourced from
  `description` instead. A dedicated short tagline, distinct from a longer
  description, can be a future change if that distinction becomes real.
- Drop the existing per-product `engine` note (e.g. Matrix → "Tuwunel
  homeserver") from the landing page entirely. This brand-vs-software
  granularity is misplaced on a marketing landing page; it is removed from
  `landingTokens.ts` and the card rendering rather than migrated to the API.
- Keep CLI and REST in lockstep: the `create-product` / `update-product` CLI
  commands gain options to set the same fields.
- Add API and CLI tests covering create/read/update of the new fields.
- Out of scope: purely presentational concerns such as the per-product accent
  color stay in the UI; they are not product data and are not moved.

## Capabilities

### New Capabilities
- `product-marketing-metadata`: the product model, API schemas, CLI, and admin
  UI carry product marketing copy (category, replaces) so the
  anonymous landing page renders it from the API instead of a hardcoded
  frontend map, with graceful fallback for empty fields.

### Modified Capabilities
<!-- None. No existing spec's requirements change; the landing page is new and
     not covered by an existing capability spec, and the product CRUD specs
     under openspec/specs/ describe UI behavior, not the field set. -->

## Impact

- **Model:** `api/app/models/core.py` — new nullable columns on `ProductORM`
  and the corresponding fields on `ProductBase` / `ProductRead` /
  `ProductCreate` / `ProductUpdate`.
- **Migration:** new Alembic revision under `api/alembic/versions/` adding the
  two columns to `product`.
- **Service:** `api/app/services/products.py` — `update_product` copies the new
  fields onto the ORM object (create already maps via `model_validate`).
- **API:** `api/app/api/products.py` — no route changes; the new fields flow
  through the existing create/read/update payloads.
- **CLI:** `api/app/cli.py` — `create-product` / `update-product` gain options
  for the new fields.
- **UI (admin):** product create/edit forms under `ui/src/components/` gain
  inputs for the new fields.
- **UI (landing):** the landing page reads the fields from the product API and
  sources the one-sentence blurb from the product's existing `description`;
  the hardcoded content in `ui/src/components/landing/landingTokens.ts` is
  removed for the moved fields, and the existing `engine` field and its card
  rendering in `AppShowcase.tsx` are deleted (presentational tokens like accent
  color remain).
- **Tests:** `api/tests/` — API (`TestClient`) and CLI (`CliRunner`) tests for
  the new fields.
