## Context

Caelus currently stores only structured metadata in the database and does not expose a static file surface. Product creation is JSON-only today, which prevents true atomic create-with-icon semantics in a single API call. This change introduces product icons as filesystem-backed static assets and upgrades product creation to support multipart form payloads carrying both product JSON and icon binary content.

Constraints and inputs for this design:
- No authorization changes in this change set.
- API static files must be publicly readable.
- Product icon files are immutable content-hash named files.
- Existing files are never deleted by replacement or product deletion.
- Product API reads expose `icon_url`, not storage-relative paths.
- `ProductCreate` payload schema remains icon-free; icon transport is a multipart file part.
- API and CLI should remain functionally aligned.

## Goals / Non-Goals

**Goals:**
- Add a nullable `rel_icon_path` field to product records.
- Expose icon reads through `ProductRead.icon_url` absolute API paths and hide `rel_icon_path` from response schemas.
- Support atomic product creation with optional icon in one request via multipart `POST /api/products`.
- Keep standalone icon replacement via `PUT /api/products/{product_id}/icon`.
- Add a safe public static file endpoint rooted at `STATIC_PATH`.
- Support icon upload during CLI `create-product` via `--icon`.
- Refactor Admin UI by extracting a dedicated New Product component and a reusable icon input component with pre-submit preview.
- Add Terraform-managed persistent static storage mounted only in API runtime.

**Non-Goals:**
- Adding Dashboard icon rendering.
- Implementing authorization or admin-only checks.
- Building custom image-editing logic beyond what an off-the-shelf UI component provides.
- Garbage collection of obsolete static files.

## Decisions

1. Use `Product.rel_icon_path` (nullable) as canonical pointer to immutable icon files in storage.
- Rationale: keeps DB small and stable while allowing static storage backends to evolve.
- Alternative considered: store image blobs in DB; rejected due to DB bloat and poorer cache semantics.

2. Add `ProductRead.icon_url` as derived API field and do not expose `rel_icon_path` in API response models.
- Rationale: API consumers should receive directly usable paths while storage internals remain encapsulated.
- Alternative considered: expose `rel_icon_path` directly; rejected because it leaks storage layout concerns.

3. Extend `POST /api/products` to accept multipart form with separate product JSON part and optional icon file part.
- Rationale: enables true atomic create-with-icon behavior in one API transaction boundary.
- Alternative considered: two-step create then upload; rejected because it is not atomically create-with-icon.

4. Keep `ProductCreate` free of icon fields.
- Rationale: preserves clean JSON model semantics and avoids encoding binary concerns into Pydantic JSON payloads.
- Alternative considered: add base64/icon fields to `ProductCreate`; rejected due to payload bloat and awkward contract.

5. Add backend image processing with Pillow (`PIL`) for deterministic output.
- Rationale: low-code path for decode/orientation/crop/resize/PNG conversion.
- Alternative considered: pass-through uploads; rejected because output shape and format requirements are strict.

6. Icon processing pipeline is server-side authoritative:
- decode image,
- normalize orientation,
- center-crop to square,
- downscale to max `256x256` with no upscaling,
- encode PNG.
- Rationale: ensures uniform icon assets regardless of client.
- Alternative considered: client-only preprocessing; rejected because clients are not trusted and CLI uploads need parity.

7. Enforce lightweight upload limits in icon ingest paths:
- max file size `10MB`,
- max input resolution `2048x2048`.
- Rationale: guards against oversized inputs and resource abuse with minimal additional code.
- Alternative considered: no limits; rejected for safety and operational predictability.

8. Use content-hash filenames under `icons/` and never mutate or delete prior files.
- Filename format: `icons/<sha1>.png` based on processed PNG bytes.
- Rationale: immutable content-addressed assets simplify caching and deduplicate identical uploads.
- Alternative considered: random UUID names per upload; rejected to avoid duplicate files for identical content.

9. Implement `GET /api/products/{id}/icon` as a `302` redirect to `/api/static/{rel_icon_path}`.
- Rationale: preserves product-specific lookup endpoint while delegating bytes/caching to static serving.
- Alternative considered: stream bytes directly from product endpoint; rejected due to duplicated static semantics.

10. Implement static serving via FastAPI/Starlette static facilities mounted at `/api/static` with root `STATIC_PATH`.
- Rationale: built-in path normalization/traversal protection, MIME handling, and conditional requests (ETag/If-None-Match) with little custom code.
- Alternative considered: custom file-serving route; rejected due to unnecessary security/caching complexity.

11. Use `react-image-crop` for Admin icon input component.
- Rationale: lightweight, active, and sufficient for preview + optional crop without heavy custom logic.
- Alternative considered: build custom crop UI; rejected for scope and maintenance cost.

12. Infrastructure: add dedicated static PVC and mount only in API pod at `/var/static`; set `STATIC_PATH=/var/static` in API runtime config.
- Rationale: API writes/serves static files; worker does not need static volume access.
- Alternative considered: share existing SQLite PVC or mount in worker too; rejected due to coupling and unnecessary access.

## Risks / Trade-offs

- [Orphan immutable files can accumulate over time] -> Accept in this phase; plan future GC strategy as separate change.
- [Large/decompression-bomb-like images can stress memory] -> Enforce file-size and resolution caps prior to costly transformations.
- [Static endpoint could expose unintended files if root is misconfigured] -> Serve strictly from `STATIC_PATH` and rely on static root isolation.
- [Multipart and JSON create contract complexity can cause client mistakes] -> Provide clear API docs and explicit validation errors for malformed multipart payloads.
- [Client-side crop UX may differ from server crop result] -> Treat server output as final and document server-authoritative transform behavior.

## Migration Plan

1. Add Alembic migration for `product.rel_icon_path` (nullable).
2. Add `STATIC_PATH` runtime config defaults for local and Terraform-managed production environments.
3. Extend product create API for multipart product+icon handling and response `icon_url` projection.
4. Add API icon replacement/read endpoints and mount static serving route.
5. Add image processing utilities and filesystem write path creation (`STATIC_PATH/icons`).
6. Extend CLI `create-product` with optional `--icon` using the same atomic create-with-icon behavior.
7. Refactor Admin page by extracting New Product component and submit multipart create requests with icon.
8. Add/adjust tests across API, CLI, UI, and infra configuration assertions.
9. Deploy API with static PVC mount before exposing icon upload UI in production.

Rollback:
- Database rollback via Alembic downgrade of `rel_icon_path` column.
- API rollback by removing icon/static routes and restoring previous create contract.
- Static files are immutable and may remain on PVC; rollback does not require cleanup.

## Open Questions

- None for this proposal phase.
