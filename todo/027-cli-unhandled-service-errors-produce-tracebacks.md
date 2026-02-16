# Issue 027: CLI Unhandled Service Errors Produce Tracebacks

## Goal
Return stable operator-facing errors instead of Python tracebacks.

## Problem
Multiple CLI commands leak unhandled exceptions on expected error paths.

## Reproduction Examples
1. Duplicate user:
   - `uv run --no-sync python -m app.cli create-user <existing-email>`
   - Actual: traceback with `IntegrityException`
2. Duplicate product:
   - `uv run --no-sync python -m app.cli create-product Mattermost dup`
   - Actual: traceback with `IntegrityException`
3. Missing user delete:
   - `uv run --no-sync python -m app.cli delete-user 999999`
   - Actual: traceback with `NotFoundException`
4. Missing product delete:
   - `uv run --no-sync python -m app.cli delete-product 999999`
   - Actual: traceback with `NotFoundException`
5. Missing template delete:
   - `uv run --no-sync python -m app.cli delete-template 1 999999`
   - Actual: traceback with `NotFoundException`

## Expected
- Friendly error line(s) on stderr.
- Exit code `1` for expected operator errors.
- No traceback for expected domain exceptions.

## Acceptance Criteria
1. CLI catches domain/service exceptions consistently across all commands.
2. Error output format is stable and documented.
3. Automated CLI tests cover duplicate and not-found paths.
