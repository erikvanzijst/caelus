## Context

The anonymous landing page renders a card per product with four pieces of
marketing copy: `category`, `replaces`, a one-sentence blurb, and an optional
`engine` note. Today these live in a hardcoded `APPS` array in
`ui/src/components/landing/landingTokens.ts` and are matched to API products by
name. The product itself already round-trips through the API as `ProductORM`
→ `ProductRead`, with `ProductCreate` / `ProductUpdate` for admin writes and an
icon stored as a relative path and derived into `icon_url` on read. The
marketing copy is product data and fits the same pattern, so it should be moved
onto the product and served by the API.

Constraints from AGENTS.md: keep REST and CLI in lockstep; put DB/ORM logic in
`api/app/services/` and call from both API and CLI; update Alembic migrations
for schema changes; add tests for new behavior.

## Goals / Non-Goals

**Goals:**
- Store product marketing copy on `ProductORM` and serve it via the API.
- Let admins set/edit the copy through both the REST API and the CLI.
- Have the landing page read the copy from the API with graceful fallback for
  empty fields, removing the hardcoded `APPS` content for those fields.

**Non-Goals:**
- Moving presentational-only tokens (e.g. per-product accent color) out of the
  UI — they are not product data and stay where they are.
- Changing the matching of products to landing cards beyond using the API as
  the source of the moved fields.
- Implementing the change. This proposal defines requirements, design, and
  tasks only.

## Decisions

- **Field names and types.** Use `category`, `replaces`, `tagline`, and
  `engine`, each a nullable text column on `product`. `tagline` is chosen for
  the one-sentence blurb to avoid the generic, overloaded name "blurb" and to
  read clearly as product copy.
  - Alternative considered: a single JSON `marketing_json` blob. Rejected —
    discrete, queryable, individually-validatable columns match how `name`,
    `description`, and `rel_icon_path` are already modeled and keep the API
    schema explicit.

- **Where the fields live in the schema hierarchy.** Add the fields to
  `ProductBase` so they are inherited by `ProductORM`, `ProductCreate`, and
  `ProductRead` (via `ProductReadBase`) in one place, and add them explicitly to
  `ProductUpdate` (which does not extend `ProductBase`) to preserve its
  partial-update semantics.
  - Alternative considered: declaring the fields only on each leaf schema.
    Rejected — more repetition and easy to drift; `ProductBase` already carries
    `name`/`description`.

- **Service write path.** `create_product` already builds the ORM via
  `ProductORM.model_validate(payload)`, so it picks up the new fields with no
  change. `update_product` copies fields field-by-field, so it must be extended
  to copy each new field when present, mirroring the existing `name` /
  `description` handling and `ProductUpdate`'s "None means leave unchanged"
  convention.

- **CLI parity.** Add options for the four fields to `create-product` and
  `update-product`, passing them through to the same service functions, so REST
  and CLI stay in lockstep.

- **Landing page consumption.** The landing page reads the fields from the
  product API response and omits any element whose field is empty. The
  hardcoded marketing content for the moved fields is removed from
  `landingTokens.ts`; any remaining presentational tokens stay.

## Risks / Trade-offs

- [Existing products have null marketing fields after migration] → The landing
  page's graceful-fallback requirement covers this; cards render without the
  missing elements until an admin fills the fields in. No data backfill is
  required by this change.
- [Removing the hardcoded `APPS` copy could regress the landing page if the API
  data is not populated first] → Sequence the rollout so the fields are
  populated (via admin UI or CLI) before/with the frontend switch; the fallback
  ensures no hard failure if a field is still empty.
- [Name-based matching of products to landing cards remains] → Out of scope
  here; this change only relocates the four content fields. Reworking the
  matching can be a follow-up.

## Migration Plan

1. Add the columns via a new Alembic revision (upgrade adds the four nullable
   text columns to `product`; downgrade drops them).
2. Ship the model/schema/service/CLI changes; existing rows keep null values.
3. Populate marketing copy for current products via the admin UI or CLI.
4. Switch the landing page to read from the API and remove the moved hardcoded
   content. Rollback is dropping the migration and reverting the frontend; the
   nullable columns make the schema change safe to roll back.

## Open Questions

- Should any of the fields enforce a maximum length (e.g. `tagline`) at the API
  layer, or remain free-form text? Defaulting to free-form nullable text unless
  a limit is requested during implementation.
