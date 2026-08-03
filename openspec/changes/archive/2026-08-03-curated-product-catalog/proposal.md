## Why

Product templates are runtime state authored by hand through the admin UI or
CLI. There is no review step, no audit trail, and no way to tell which upstream
application version a product is pinned to without querying the database. This
blocks the goal of an autonomous agent that detects new upstream releases and
proposes upgrades: a proposal needs somewhere reviewable to land, and today an
"upgrade Immich to v3.1.0" pull request would contain an empty diff.

At the same time, the hands-on authoring loop — create a product, tweak system
values, iterate on a Helm chart until it works — is how new products are
onboarded and must not regress.

## What Changes

- Introduce `products/catalog/<slug>.yaml` as version-controlled desired state
  for *published* products. Each file declares the product's marketing metadata,
  its Helm chart reference, its system values (including the pinned application
  image tag), its user values JSON schema, and the metadata needed to detect
  new upstream releases.
- Add a `CatalogReconciler` that applies the catalog to the database. It has
  exactly two verbs: insert a `ProductTemplateVersion` when no existing
  non-deleted template for that product matches the catalog spec, and repoint
  `product.template_id` at the match. It never updates or deletes a template
  row, so the table becomes an append-only version ledger.
- Split products into **curated** (git-authored, reconciler-managed) and
  **non-curated** (database-authored, unchanged behavior). `product.curated` is
  the reconciler's selector, so non-curated products are provably untouched.
- Add `product.visibility` (`public` | `admin`) controlling whether a product
  appears in the end-user product list. Admins always see every non-deleted
  product regardless of `curated` or `visibility`. Visibility is runtime state,
  not catalog state: it is absent from the catalog document, editable in the
  admin UI for every product including curated ones, and never written by the
  reconciler after a product is created. Products the reconciler creates start
  hidden, so merging a catalog change can never by itself publish a product.
- Add `product.slug` as the stable key joining a catalog file to its product
  row, so renaming a product does not orphan its catalog entry.
- Add `product_template_version.catalog_commit`, recording the git commit that
  produced a template row. Written once on insert from the `GIT_COMMIT`
  environment variable already present in the API image; never read by
  application code.
- Add `caelus catalog` CLI verbs: `apply` (run by the init container), `curate`
  (write a product's catalog file and icon from current database state — the
  graduation path for a hand-tuned product, which reports that the change must
  still be committed and merged to take effect), and `lint` (CI validation on
  pull requests).
- Make catalog file presence the sole carrier of curation: adding a file
  curates a product, removing one releases it, and only the reconciler writes
  `curated` and `slug`. There is no command to curate or uncurate, so the two
  cannot disagree. A catalog directory that cannot be read is an error rather
  than a mass release, since failing to read the desired state is not the same
  as the desired state being empty; an empty directory is valid and simply means
  nothing is catalog-managed.
- Bake `products/catalog/` into the API image and apply it from a new init
  container running after the existing `migrate` container. A malformed catalog
  fails the init container, so new pods never become ready and the previous
  ReplicaSet keeps serving. No cluster credentials are needed in CI and no
  runtime git access is required.
- **BREAKING** (admin-facing only): curated products become read-only through
  the REST API, CLI, and admin UI. Product field edits, template creation, and
  canonical-template selection for curated products must go through a pull
  request. A `--force` break-glass path remains for modifications, and forced
  writes leave `catalog_commit` null so the drift is visible and self-heals on
  next rollout. Deletion of a curated product or its templates is never
  forceable — it requires removing the product's catalog file first — because a
  force-deleted product is simply recreated under a new id by the next
  reconciliation.

Out of scope: upgrading running deployments to a new canonical template
(deployments keep their current template until an operator acts), plan and
plan-template catalog management, and the release-detection agent itself.

## Capabilities

### New Capabilities
- `product-catalog-format`: the `products/catalog/<slug>.yaml` file contract —
  required blocks and fields, the upstream release-detection metadata, and
  validation rules.
- `catalog-reconciliation`: `CatalogReconciler` semantics — spec matching and
  idempotency, template insertion, canonical repointing, adoption of existing
  non-curated products, uncuration when a catalog file is removed, the guard
  against an unreadable catalog directory, and how the reconciler is invoked
  during rollout.
- `curated-product-governance`: the `slug`, `curated`, and `catalog_commit`
  columns; service-layer write guards for curated products; the break-glass
  path; and the rule that only the reconciler writes `curated` and `slug`.
- `product-visibility`: the `visibility` column, its effect on the end-user
  product list versus admin listings, and its editability for every product.
- `catalog-cli`: the `caelus catalog apply|curate|lint` command surface and its
  REST parity obligations.

### Modified Capabilities
- `admin-product-detail`: inline editing of the product header is disabled for
  curated products, which are shown as catalog-managed instead.
- `admin-template-tabs`: the "New" template tab and the "Make canonical" button
  are disabled for curated products.
- `product-marketing-metadata`: `category` and `replaces` remain editable via
  REST, CLI, and admin UI only for non-curated products; for curated products
  they are sourced from the catalog file.

## Impact

- **Database**: new columns `product.slug`, `product.curated`,
  `product.visibility`, `product_template_version.catalog_commit`; Alembic
  migration backfilling existing products as `curated=false`,
  `visibility='public'` to preserve current behavior.
- **API/services**: `api/app/services/products.py` and
  `api/app/services/templates.py` gain write guards; new
  `api/app/services/catalog.py`; product list endpoints gain visibility
  filtering.
- **CLI**: new `caelus catalog` command group in `api/app/cli.py`.
- **UI**: `ui/src/components/SelectedProduct.tsx` and the template tab
  components render curated products read-only.
- **Repo**: new top-level `products/catalog/` directory containing one YAML
  file per published product, seeded from the current database via
  `catalog curate`.
- **Build/deploy**: `Dockerfile` copies `products/catalog/`; the API pod
  template gains a `catalog` init container after `migrate`. The master CI
  build must not gain path filters, or catalog-only merges would not roll out.
- **Concurrency**: `catalog apply` takes a Postgres advisory lock so concurrent
  init containers across replicas cannot double-insert.
