## Why

Caelus products currently have no visual identity and the API cannot serve static assets from a controlled filesystem location. We need product icon upload and public static file delivery now to unblock richer admin workflows while keeping infrastructure simple (filesystem + PVC) and compatible with current API/CLI patterns.

## What Changes

- Add product icon support to the data model with a new nullable `Product.rel_icon_path` field storing a relative path under `STATIC_PATH`.
- Expose product icon in API reads as `ProductRead.icon_url` (absolute API path like `/api/static/icons/<sha1>.png`) and do not expose `rel_icon_path` in API response models.
- Extend `POST /api/products` to support multipart form creation with two parts:
  - one JSON part for product payload,
  - one binary icon part,
  so product + icon can be created atomically in one request.
- Keep `ProductCreate` free of icon attributes; icon input is transported only via multipart file field.
- Add API endpoint `PUT /api/products/{product_id}/icon` for binary image upload, server-side square crop, PNG conversion, and max-size downscaling.
- Add API endpoint `GET /api/products/{product_id}/icon` that returns a `302` redirect to `/api/static/{rel_icon_path}` when icon is present.
- Add public API endpoint `GET /api/static/{path}` to serve files rooted at `STATIC_PATH` with path traversal protection, MIME type handling, ETag, and `If-None-Match` support.
- Make uploaded icon files immutable: each upload resolves to a content-hash filename and updates `rel_icon_path`; previously uploaded files remain on disk.
- Enforce lightweight upload caps at icon ingest boundary: max upload size `10MB`, max source image resolution `2048x2048`.
- Extend CLI parity by adding `create-product --icon <path>` that creates the product with icon atomically.
- Refactor Admin UI by extracting the New Product widget from `Admin.tsx` into a dedicated component and adding a dedicated icon input component with pre-submit preview.
- Keep Dashboard UI unchanged (no icon display yet).
- Add Terraform support for static storage: dedicated PVC mounted only in API pods; worker pods must not mount static storage.

## Capabilities

### New Capabilities
- `product-icons`: Product icon data model, upload/update behavior, API/CLI create flows, and Admin UI create-product icon workflow.
- `api-static-file-serving`: Public static file serving rooted at `STATIC_PATH` with safe path normalization, cache validators, and redirect integration from product icon reads.

### Modified Capabilities
- None.

## Impact

- Affected API code: `api/app/models.py`, `api/app/api/products.py`, `api/app/main.py`, product create request/response schemas, new/updated static and image utility modules, and service-layer product logic.
- Affected CLI code: `api/app/cli.py` create-product command path/file upload flow.
- Affected UI code: `ui/src/pages/Admin.tsx`, new admin product form component(s), API client helpers for multipart upload.
- Affected infrastructure: Terraform PVC/config/env for `STATIC_PATH`, API deployment mounts, worker deployment mount exclusions.
- Affected dependencies: backend image-processing dependency (Pillow) and one frontend crop/preview package.
- Tests required across API, CLI, UI component behavior, and static endpoint caching/sanitization edge cases.
