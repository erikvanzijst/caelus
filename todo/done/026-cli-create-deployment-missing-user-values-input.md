# Issue 026: CLI `create-deployment` Missing `user_values_json` Input

## Goal
Align CLI deployment creation inputs with REST deployment creation payload.

## Problem
REST deployment create payload supports `user_values_json`, but CLI has no way to provide it.

## Impact
CLI cannot create deployments with user-provided values that are possible through REST.

## Acceptance Criteria
1. Add a CLI option for user values (e.g. JSON string or file path).
2. Parse/validate into `user_values_json` and pass to service.
3. Document expected format in CLI help.
