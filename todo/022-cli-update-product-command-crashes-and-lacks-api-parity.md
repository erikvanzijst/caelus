# Issue 022: CLI `update-product` Crashes And Lacks API Parity

## Goal
Make CLI product updates functional and aligned with `PUT /products/{product_id}`.

## Problem
`update-product` calls a non-existent service function and exits with a traceback.

## Reproduction
1. `cd api`
2. `uv run --no-sync python -m app.cli update-product 1 1`

## Actual
- Crash: `AttributeError: module 'app.services.products' has no attribute 'update_product_template'`
- Exit code: `1`

## Expected
- Command should call `product_service.update_product(...)` and return a stable operator-facing error format.
- Behavior should match REST update semantics.

## API Parity Gap
REST `PUT /products/{product_id}` supports both:
1. `template_id`
2. `description`

Current CLI command only attempts template update and has no description update path.

## Acceptance Criteria
1. `update-product` uses existing service API and no longer crashes.
2. CLI supports all updateable product fields exposed by REST.
3. Not-found/validation errors return stable non-traceback output and exit `1`.
