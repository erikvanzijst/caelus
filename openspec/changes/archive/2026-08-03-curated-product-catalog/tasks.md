## 1. Phase 1 — Product visibility

- [x] 1.1 Add `visibility` to `ProductBase`/`ProductORM` in `api/app/models/core.py` as a non-null column accepting `public` and `admin`, defaulting to `admin` for new rows
- [x] 1.2 Add an Alembic migration creating the column and backfilling every existing product to `public`
- [x] 1.3 Add `visibility` to `ProductCreate`, `ProductUpdate`, and `ProductRead`
- [x] 1.4 Filter end-user product listings to `visibility = 'public'` in `api/app/services/products.py`, leaving admin listings filtered on `deleted_at` alone
- [x] 1.5 Add `--visibility` to `create-product` and `update-product` in `api/app/cli.py`
- [x] 1.6 Add `visibility` to `ui/src/api/types.ts` and to the product update mutation
- [x] 1.7 Build a `ProductVisibilityControl` component under `ui/src/components/` showing the current setting and persisting changes via the product update API; render it in the product detail panel rather than inlining it
- [x] 1.8 Write tests: hidden products excluded from the end-user list, admins see all non-deleted products, migration backfills existing rows to `public`, new products default to `admin`
- [x] 1.9 Write tests: changing visibility to `public` makes a product appear in the end-user list and to `admin` removes it, with existing deployments unaffected; REST and CLI produce identical results

## 2. Phase 2 — Governance columns and write guards

- [x] 2.1 Add `slug` (nullable, unique among non-deleted) and `curated` (non-null, default false) to `ProductORM`
- [x] 2.2 Add `catalog_commit` (nullable text) to `ProductTemplateVersionORM`; do not add it to the create/read schemas
- [x] 2.3 Add an Alembic migration for all three columns, including the partial unique index on `slug`, backfilling `curated = false`
- [x] 2.4 Add `slug` and `curated` to `ProductRead` so the admin UI can branch on them
- [x] 2.5 Implement `_assert_mutable(product, *, force=False)` in `api/app/services/products.py`, raising `ValidationException` naming the product's catalog file
- [x] 2.6 Call the guard from `update_product`, `delete_product` in `products.py` and from `create_template`, `delete_template` in `api/app/services/templates.py`; exempt `visibility`-only updates from the guard; the two delete paths SHALL ignore `force` and always refuse for a curated product, with an error directing the operator to remove the product's catalog file first
- [x] 2.7 Expose the break-glass override as a `force` query parameter (default false) on the product update, product delete, template create, and template delete endpoints — never in the request body, since the delete endpoints are 204 with no body and `update_product` is multipart; document the resulting 400 in each endpoint's `responses={}` block
- [x] 2.8 Add the matching `--force` flag to the corresponding CLI commands, and log every forced write at WARNING with the acting user and product slug
- [x] 2.9 Ensure forced template creation leaves `catalog_commit` null
- [x] 2.10 Write tests: curated products reject writes via REST and CLI identically, non-curated products are unaffected, forced writes succeed and leave `catalog_commit` null
- [x] 2.11 Write tests: force does NOT permit deleting a curated product or its templates via REST or CLI; deletion succeeds once the catalog file has been removed and rolled out; non-curated deletion is unaffected

## 3. Phase 2 — Admin UI read-only mode

- [x] 3.1 Render the product header read-only for curated products in `ui/src/components/SelectedProduct.tsx`, naming the catalog file
- [x] 3.2 Make the `category` and `replaces` controls read-only for curated products, naming the catalog file, while leaving the visibility control enabled
- [x] 3.3 Hide the "New" template tab for curated products
- [x] 3.4 Hide the "Make canonical" button for curated products and indicate the canonical template is catalog-set
- [x] 3.5 Extract the catalog-managed notice into its own component under `ui/src/components/` rather than inlining it

## 4. Phase 3 — Catalog format and validation

- [x] 4.1 Define the catalog document as Pydantic models (`schema_version`, `product`, `upstream`, `template` blocks) in a new `api/app/services/catalog.py`, with `extra="forbid"` so a mistyped key — or a `visibility` key, which is not catalog-managed — is a hard error rather than a silently ignored value
- [x] 4.2 Implement loading with `yaml.safe_load` plus per-document validators: `schema_version` recognized, slug matches the filename stem, icon path resolves inside the catalog directory
- [x] 4.3 Implement directory-level validation that cannot live on a single document: slugs unique across files, and every referenced icon file present and processable
- [x] 4.4 Meta-validate `template.values_schema` with `jsonschema.validators.validator_for(schema).check_schema(schema)` so the document's own `$schema` dialect is honored; note `SchemaError` is not a subclass of `ValidationError` and must be caught explicitly
- [x] 4.5 Validate that `upstream.match` compiles as a regular expression and defines a `version` named capture group
- [x] 4.6 Emit the generated JSON Schema for the catalog document (`model_json_schema()`) so catalog files can reference it for editor completion
- [x] 4.7 Implement `spec_hash()` over `chart_ref`, `chart_version`, `chart_digest`, `system_values_json`, `values_schema_json` using canonical sorted-key JSON
- [x] 4.8 Write tests: key ordering does not change the hash, each validation rule rejects its bad input with a message naming the offending file, and an unknown key in any block is rejected

## 5. Phase 3 — CatalogReconciler

- [x] 5.1 Implement `CatalogReconciler` in the same new `api/app/services/catalog.py` as the document models — constructed as `CatalogReconciler(session=..., catalog_dir=..., commit_sha=...)` with an `apply()` entry point, mirroring `DeploymentReconciler`'s shape. Do NOT add it to `api/app/services/reconcile.py`: it shares no dependencies with that module (no `Provisioner`, no Helm, no `reconcile_constants`), runs once at startup rather than per job, and aborts the whole run on failure rather than marking one deployment errored
- [x] 5.2 Wrap `apply()` in a single transaction and a Postgres advisory lock so concurrent init containers cannot double-insert
- [x] 5.3 Error and apply nothing if the catalog directory does not exist or cannot be read, so a config fault is not mistaken for an empty desired state; an existing but empty directory is valid and reconciles normally
- [x] 5.4 Implement per-product apply: resolve by slug, else adopt a non-curated product by case-insensitive name match, else create; then set product fields and `curated = true`. Initialize `visibility` to `admin` only when creating, and never write it on a later run
- [x] 5.5 Implement template matching by spec hash across non-deleted templates, ignoring `catalog_commit`, inserting only on no match and stamping `catalog_commit` from `GIT_COMMIT`
- [x] 5.6 Repoint `product.template_id` to the matched or inserted template
- [x] 5.7 Implement icon materialization: read the `icon` path relative to the catalog directory, reuse `process_icon`/`generate_icon_filename`/`save_icon` from `api/app/services/images.py`, and set `rel_icon_path`
- [x] 5.8 Make icon materialization skip the write only when the content-addressed path matches AND the file exists in `static_path`, so a fresh volume is repopulated; fail the run on a missing or unprocessable icon
- [x] 5.9 Implement uncuration: clear `curated` and `slug` for any curated product whose slug no catalog file declares, leaving its templates, `template_id`, `visibility`, and deployments untouched, and log each release
- [x] 5.10 Verify every product-selecting query filters `curated = true`
- [x] 5.11 Write tests: idempotent re-run inserts nothing; non-curated products byte-identical after a run; adoption sets `curated` without inserting a template; new spec inserts and repoints; existing deployments' `applied_template_id` unchanged
- [x] 5.12 Write icon tests: first run materializes the file; unchanged icon is not rewritten; a correct `rel_icon_path` with an empty `static_path` is repopulated; an icon change updates the product without inserting a template row
- [x] 5.13 Write uncuration tests: removing a file clears `curated` and `slug` while leaving templates, `template_id`, `visibility`, and deployments intact; restoring the file re-adopts by name; a missing catalog directory errors and uncurates nothing; an existing empty directory reconciles successfully
- [x] 5.14 Write visibility tests: a created product starts `admin`; an admin's change to a curated product's visibility survives a subsequent reconciliation; adoption leaves visibility unchanged

## 6. Phase 3 — Catalog CLI

- [x] 6.1 Add the `catalog` command group to `api/app/cli.py`
- [x] 6.2 Implement `catalog apply --dir DIR [--dry-run]`, reporting planned actions in dry-run and exiting non-zero without persisting on failure
- [x] 6.3 Implement `catalog curate SLUG [--dir DIR]`, writing the product's catalog document and its icon into the catalog directory from database state, leaving `curated` and `slug` untouched, and printing the files written plus a reminder that the change must be committed and merged to take effect
- [x] 6.4 Implement `catalog lint --dir DIR` performing file-only validation with no database connection
- [x] 6.5 Write the round-trip test: `curate` every product, apply, assert zero new template rows and unchanged `template_id`; assert `curate` alone leaves `curated` and `slug` unchanged
- [x] 6.6 Write tests: dry-run writes nothing, one invalid file aborts the whole run, lint runs with no database configured, and lint rejects a document declaring `visibility`

## 7. Phase 3 — Seed the catalog

- [x] 7.1 Run `catalog curate` for each existing product to generate its `products/catalog/<slug>.yaml` and `products/catalog/icons/<slug>.png`; do not hand-author either
- [x] 7.2 Add the `upstream` block to each generated file, choosing the correct `source.type` and `match` per product
- [x] 7.3 Verify with `catalog apply --dry-run` that the seed is a no-op: no products created, no templates inserted, no canonical pointers moved
- [x] 7.4 Commit `products/catalog/` and confirm after rollout that each product is `curated = true` with an unchanged `template_id` and still renders an icon

## 8. Phase 4 — Rollout wiring

- [x] 8.1 Copy `products/catalog/` into the API image in the Dockerfile and ensure `GIT_COMMIT` is set at build time
- [x] 8.2 Add a `catalog` init container running `caelus catalog apply` after the existing `migrate` init container in the Terraform pod template
- [x] 8.3 Add `catalog lint` to `.github/workflows/ci.yml` for pull requests
- [x] 8.4 Add a comment where the master build is configured recording that path filters would break catalog delivery
- [x] 8.5 Verify on dev that an invalid catalog fails the init container and leaves the previous pods serving

## 9. Documentation

- [x] 9.1 Document the catalog format, the curated/non-curated split, and the graduation path via `catalog curate` in `api/README.md`
- [x] 9.2 Document the break-glass `--force` path and its self-healing behavior
- [x] 9.3 Note in `AGENTS.md` that the `catalog` CLI group is intentionally exempt from REST parity
