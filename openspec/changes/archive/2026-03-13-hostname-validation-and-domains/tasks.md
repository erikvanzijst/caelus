## 1. Pydantic Settings

- [x] 1.1 Add `pydantic-settings` to `api/pyproject.toml` dependencies and run `uv sync`
- [x] 1.2 Replace `api/app/config.py` with `CaelusSettings(BaseSettings)` class using `env_prefix="CAELUS_"`. Include fields: `database_url`, `static_path`, `log_level`, `lb_ips`, `wildcard_domains`, `reserved_hostnames`. Add `get_settings()` with `@lru_cache`
- [x] 1.3 Update `api/app/db.py` to use `get_settings().database_url` instead of `os.environ.get("DATABASE_URL")`
- [x] 1.4 Update `api/app/logging_config.py` to use `get_settings().log_level` instead of `os.environ.get("CAELUS_LOG_LEVEL")`
- [x] 1.5 Update `api/app/main.py` to use `get_settings().static_path` instead of `get_static_path()`. Remove old `get_static_url_base()` if no longer needed
- [x] 1.6 Update Terraform env var references in `tf/` from `DATABASE_URL` → `CAELUS_DATABASE_URL`, `STATIC_PATH` → `CAELUS_STATIC_PATH`
- [x] 1.7 Write tests for `CaelusSettings` — default values, env var loading, list field parsing
- [x] 1.8 Run existing test suite and fix any breakage from config changes

## 2. Rename domainname to hostname — backend

- [x] 2.1 Create Alembic migration: rename column `domainname` → `hostname`, rename indexes `uq_domainname_active` → `uq_hostname_active`, `ix_deployment_domainname` → `ix_deployment_hostname`, update `uq_deployment_active` column reference
- [x] 2.2 Update `DeploymentORM` in `api/app/models.py`: rename field, update index definitions
- [x] 2.3 Update `DeploymentRead` in `api/app/models.py`: rename `domainname` → `hostname`
- [x] 2.4 Rename `_iter_domainname_paths()` → `_iter_hostname_paths()` and `_derive_domainname()` → `_derive_hostname()` in `api/app/services/deployments.py`. Change schema title check to `title.lower() == "hostname"`. Rename all local variables
- [x] 2.5 Update all Python test files: replace `domainname` with `hostname` in assertions, fixtures, schema definitions (`title: "domainname"` → `title: "hostname"`), and test function names (~15 files)
- [x] 2.6 Update chart `values.schema.json` files: add `"title": "hostname"` to the host/serverName fields in `products/helloworld/chart/`, `products/matrix/chart/`, `products/immich/chart/`
- [x] 2.7 Run full backend test suite and fix any remaining references

## 3. Rename domainname to hostname — frontend

- [x] 3.1 Update `Deployment` interface in `ui/src/api/types.ts`: rename `domainname` → `hostname`
- [x] 3.2 Update `ui/src/pages/Dashboard.tsx`: replace all `deployment.domainname` references with `deployment.hostname`
- [x] 3.3 Update `ui/src/api/endpoints.test.ts`: rename fixture data and assertions (N/A — no UI test files exist)

## 4. Hostname validation service

- [x] 4.1 Add `HostnameException` class with `reason: str` attribute to `api/app/services/errors.py`
- [x] 4.2 Create `api/app/services/hostnames.py` with `require_valid_hostname_for_deployment(session, fqdn)` function
- [x] 4.3 Implement `_check_format(fqdn)` — RFC 952/1123 validation (max 253 chars, labels 1-63 chars, alphanumeric + hyphens, no leading/trailing hyphens per label)
- [x] 4.4 Implement `_check_reserved(fqdn, settings)` — lookup against `settings.reserved_hostnames`
- [x] 4.5 Implement `_check_available(session, fqdn)` — query `DeploymentORM` for active deployments with matching hostname
- [x] 4.6 Implement `_check_resolving(fqdn, settings)` — sync DNS resolution via `socket.getaddrinfo()`, verify all IPs ⊆ `settings.lb_ips`, skip when `lb_ips` is empty
- [x] 4.7 Write unit tests for each check function (format edge cases, reserved matching, availability queries, DNS resolution with mocked socket)
- [x] 4.8 Write integration test for `require_valid_hostname_for_deployment` orchestration and short-circuit behavior

## 5. Hostname check API endpoint

- [x] 5.1 Create `api/app/api/hostnames.py` with `GET /api/hostnames/{fqdn}` sync endpoint. Returns `HostnameCheck` response model (`fqdn: str`, `reason: str | None`)
- [x] 5.2 Register hostname router in `api/app/main.py` with `/api` prefix
- [x] 5.3 Register `HostnameException` handler in `api/app/api/utils.py` to return HTTP 200 with the reason (or consider returning it directly in the endpoint)
- [x] 5.4 Write API integration tests: usable hostname, invalid format, reserved, in-use, not-resolving

## 6. Domains list API endpoint

- [x] 6.1 Add `GET /api/domains` endpoint to the hostnames router. Returns `settings.wildcard_domains` as `list[str]`. No auth dependency
- [x] 6.2 Write API test: configured domains returned, empty list when unconfigured

## 7. Server-side hostname enforcement

- [x] 7.1 Wire `require_valid_hostname_for_deployment()` into `create_deployment()` in `api/app/services/deployments.py` — call after `_derive_hostname()`, before flush. Skip if hostname is `None`
- [x] 7.2 Wire `require_valid_hostname_for_deployment()` into `update_deployment()` — same pattern, with `exclude_deployment_id` to avoid self-conflict
- [x] 7.3 Register `HostnameException` in API exception handlers to map to HTTP 409
- [x] 7.4 Update existing deployment tests: constraint tests now expect `HostnameException` instead of `IntegrityException` since service-level validation fires first
- [x] 7.5 Write new tests: deployment creation rejected when hostname is reserved, in-use, or not resolving

## 8. UI HostnameField component

- [x] 8.1 Add `checkHostname(fqdn)` and `listDomains()` functions to `ui/src/api/endpoints.ts`
- [x] 8.2 Add `HostnameCheckResult` type (`fqdn: string`, `reason: string | null`) to `ui/src/api/types.ts`
- [x] 8.3 Create `ui/src/components/HostnameField.tsx` with dual-mode input (Caelus wildcard prefix + domain dropdown, or custom FQDN text input)
- [x] 8.4 Implement debounced validation (~400ms) calling `GET /api/hostnames/{fqdn}` via React Query or `useEffect` + `AbortController`
- [x] 8.5 Implement status icon display: green CheckCircle, red Error with tooltip, CircularProgress spinner
- [x] 8.6 Handle edge cases: empty input (no API call, no icon), switching modes (reset state), no wildcard domains available (default to custom mode)

## 9. Integrate HostnameField into UserValuesForm

- [x] 9.1 Modify `UserValuesForm.tsx` to detect fields where `field.title?.toLowerCase() === "hostname"` and render `<HostnameField>` instead of `<TextField>`
- [x] 9.2 Fetch wildcard domains via React Query in `UserValuesForm` (or in `HostnameField`) and pass as prop
- [x] 9.3 Ensure the `onChange` callback from `HostnameField` feeds into the form's flattened state at the correct dot-notation path
- [x] 9.4 Verify end-to-end: selecting a product with a hostname-titled schema field renders the HostnameField, typing triggers validation, and form submission includes the hostname in `user_values_json`

## 10. Documentation

- [x] 10.1 Add "UI Conventions" section to AGENTS.md documenting React component extraction guidelines
