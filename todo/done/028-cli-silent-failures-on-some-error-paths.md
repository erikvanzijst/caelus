# Issue 028: CLI Silent Failures On Some Error Paths

## Goal
Ensure failing CLI commands provide clear diagnostics.

## Problem
Some commands exit non-zero without any error message.

## Reproduction Examples
1. Missing product on template create:
   - `uv run --no-sync python -m app.cli create-template 999999 oci://example/chart 1.0.0`
   - Actual: blank output, exit `1`
2. Missing deployment delete:
   - `uv run --no-sync python -m app.cli delete-deployment 1 999999`
   - Actual: blank output, exit `1`

## Expected
- Clear message indicating resource not found and relevant identifiers.
- Exit code `1`.

## Acceptance Criteria
1. All expected failure paths print actionable error text.
2. No blank-failure behavior remains.
3. CLI tests assert both exit code and stderr content.
