## Why

Users can currently enter any string as a hostname when deploying an app — there is no format validation, no check that it resolves to Caelus' load balancer, and no protection against reserved or already-taken hostnames. This leads to broken deployments and confusing errors that surface only at provisioning time. Additionally, the field is named "domainname" throughout the stack, which is misleading — it's a hostname (FQDN). Fixing this now prevents accumulating more code built on the wrong name.

## What Changes

- **BREAKING**: Rename the `domainname` field to `hostname` across the entire stack — DB column, ORM model, API response, UI types, schema title convention (`title: "hostname"`), service functions, and all tests. No backward compatibility shim; existing templates in the database will be manually updated.
- **BREAKING**: Replace ad-hoc environment variable configuration with a Pydantic `BaseSettings` class (`CaelusSettings`). All env vars move to a `CAELUS_` prefix (`CAELUS_DATABASE_URL`, `CAELUS_STATIC_PATH`, `CAELUS_LOG_LEVEL`). Three new settings: `CAELUS_LB_IPS`, `CAELUS_WILDCARD_DOMAINS`, `CAELUS_RESERVED_HOSTNAMES`.
- New hostname validation service with a single public function `require_valid_hostname_for_deployment()` that checks format (RFC 952/1123), reserved hostnames (blacklist), availability (no active deployment using it), and DNS resolution (all resolved IPs must be within configured LB IPs).
- New API endpoint `GET /api/hostnames/{fqdn}` for real-time hostname validation, returning `{ "fqdn": "...", "reason": null | "invalid" | "reserved" | "in_use" | "not_resolving" }`.
- New API endpoint `GET /api/domains` returning the list of Caelus-provided wildcard domains.
- Server-side hostname enforcement: `create_deployment()` and `update_deployment()` call the validation service before DB flush.
- New `HostnameField` React component with dual-mode input (Caelus wildcard domain + prefix, or custom FQDN) and real-time validation with debounced API calls and status indicator icons.
- `UserValuesForm` modified to detect `title: "hostname"` fields and render `HostnameField` instead of a plain text input.
- Documentation: add React component extraction convention to AGENTS.md.

## Capabilities

### New Capabilities
- `hostname-validation`: Server-side hostname validation service — format, blacklist, availability, and DNS resolution checks. Single public function API with exception-based error reporting.
- `hostname-check-endpoint`: REST endpoint for real-time hostname usability checks (`GET /api/hostnames/{fqdn}`).
- `wildcard-domains-endpoint`: REST endpoint to list Caelus-provided wildcard domains (`GET /api/domains`).
- `pydantic-settings`: Centralized configuration via Pydantic `BaseSettings` with `CAELUS_` prefix, replacing ad-hoc `os.environ.get()` calls.
- `hostname-field-ui`: React component for hostname input with dual-mode (wildcard/custom), real-time validation, and status indicators.

### Modified Capabilities
- `deployment-create-contract`: The `domainname` field is renamed to `hostname` in deployment read responses, schema title convention changes from `"domainname"` to `"hostname"`, and create/update now perform hostname validation before persisting.

## Impact

- **Database**: New Alembic migration to rename column and indexes.
- **API contract**: `DeploymentRead.domainname` becomes `DeploymentRead.hostname` — breaking change for any API consumers.
- **Configuration**: All env var names change to `CAELUS_` prefix — Terraform deployment configs and local dev `.env` files must be updated.
- **Affected code**: `api/app/models.py`, `api/app/services/deployments.py`, `api/app/config.py`, `api/app/db.py`, `api/app/logging_config.py`, `api/app/main.py`, `api/app/api/users.py`, `ui/src/api/types.ts`, `ui/src/pages/Dashboard.tsx`, `ui/src/components/UserValuesForm.tsx`, all chart `values.schema.json` files, ~15 test files.
- **New files**: `api/app/services/hostnames.py`, `api/app/api/hostnames.py`, `ui/src/components/HostnameField.tsx`.
- **Dependencies**: `pydantic-settings` package added to API dependencies.
