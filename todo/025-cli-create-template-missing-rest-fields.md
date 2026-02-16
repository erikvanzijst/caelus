# Issue 025: CLI `create-template` Missing REST Payload Fields

## Goal
Align CLI template creation with REST template creation payload.

## Problem
CLI `create-template` only accepts:
1. `product_id`
2. `chart_ref`
3. `chart_version`

REST schema supports additional fields that cannot be set via CLI:
1. `chart_digest`
2. `version_label`
3. `default_values_json`
4. `values_schema_json`
5. `capabilities_json`

## Impact
CLI cannot perform full-fidelity template authoring supported by API.

## Acceptance Criteria
1. CLI supports all REST create-template fields via options/JSON input.
2. Validation and error behavior mirrors REST/service constraints.
3. CLI help documents all supported template payload fields.
