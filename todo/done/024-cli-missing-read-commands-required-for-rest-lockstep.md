# Issue 024: CLI Missing Read Commands Required For REST Lockstep

## Goal
Bring CLI read capabilities to functional lockstep with REST resources.

## Problem
REST exposes single-resource read endpoints that have no CLI equivalents.

## Missing CLI Commands
1. `get-user` parity for `GET /users/{user_id}`
2. `get-product` parity for `GET /products/{product_id}`
3. `get-template` parity for `GET /products/{product_id}/templates/{template_id}`
4. `get-deployment` parity for `GET /users/{user_id}/deployments/{deployment_id}`

## Impact
Operators cannot retrieve one specific resource via CLI without scanning list output.

## Acceptance Criteria
1. Add the four commands with argument shapes that mirror REST path params.
2. Use service layer (no direct DB logic in CLI).
3. Not-found behavior is stable and consistent with other CLI commands.
