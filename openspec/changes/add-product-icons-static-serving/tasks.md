## 1. Data Model And Migration

- [ ] 1.1 Add nullable `rel_icon_path` to product ORM and add derived `ProductRead.icon_url` while keeping storage-relative path internal.
- [ ] 1.2 Generate and curate Alembic migration for `product.rel_icon_path`.
- [ ] 1.3 Add/update model and API tests to verify `icon_url` read behavior before and after icon upload, and confirm `rel_icon_path` is not exposed in API responses.

## 2. Static Serving Foundation

- [ ] 2.1 Add `STATIC_PATH` configuration with local default and startup/static-root initialization.
- [ ] 2.2 Mount public `/api/static` serving rooted at `STATIC_PATH` using framework static facilities.
- [ ] 2.3 Add API tests for static file serving, traversal blocking, ETag presence, and `If-None-Match` `304` behavior.

## 3. Product Icon API

- [ ] 3.1 Extend `POST /api/products` to accept multipart form input containing product JSON part and optional icon file part.
- [ ] 3.2 Ensure multipart create-with-icon path is atomic: icon failures must not leave persisted product records.
- [ ] 3.3 Keep `ProductCreate` icon-free and validate malformed multipart/product JSON with stable client errors.
- [ ] 3.4 Implement `PUT /api/products/{product_id}/icon` with multipart file input handling.
- [ ] 3.5 Implement server-side image pipeline (orientation normalize, center square crop, max 256 downscale without upscaling, PNG output).
- [ ] 3.6 Enforce icon ingest caps (`10MB` max payload, `2048x2048` max source dimensions) with stable client error responses.
- [ ] 3.7 Persist icons as immutable UUID-based files under `icons/` and update `product.rel_icon_path` without deleting old files.
- [ ] 3.8 Implement `GET /api/products/{product_id}/icon` returning `302` redirect to `/api/static/{rel_icon_path}` or `404` when absent.
- [ ] 3.9 Add API tests covering multipart create success/failure atomicity, successful upload, replacement immutability semantics, missing product/icon, and cap validation failures.

## 4. CLI Parity

- [ ] 4.1 Extend `create-product` with optional `--icon <path>` input.
- [ ] 4.2 Implement create-with-icon command flow against the multipart create contract as atomic from operator perspective.
- [ ] 4.3 Add CLI tests for create-product with valid icon and failure rollback behavior.

## 5. Admin UI Refactor And Icon UX

- [ ] 5.1 Extract New Product widget from `Admin.tsx` into a dedicated component.
- [ ] 5.2 Add dedicated icon input component using `react-image-crop` with pre-submit image preview.
- [ ] 5.3 Add client API helper for multipart create requests and non-JSON upload requests.
- [ ] 5.4 Implement create-with-icon submit flow using single multipart `POST /api/products` request.
- [ ] 5.5 Add/adjust UI tests for preview behavior and create-with-icon success/failure flows.

## 6. Terraform And Runtime Configuration

- [ ] 6.1 Add Terraform PVC for static assets.
- [ ] 6.2 Mount static PVC and set `STATIC_PATH=/var/static` in API deployment only.
- [ ] 6.3 Ensure worker deployment does not mount static PVC and does not depend on `STATIC_PATH`.
- [ ] 6.4 Validate Terraform configuration and update docs for static storage runtime expectations.

## 7. Documentation And Verification

- [ ] 7.1 Update API README for multipart product create contract, icon/static endpoints, and `icon_url` response behavior.
- [ ] 7.2 Update UI README with New Product component split and icon upload UX notes.
- [ ] 7.3 Run backend and UI test suites relevant to icon/static behavior and record outcomes.
