## Why

Custom domain validation currently resolves the user's hostname to IP addresses and checks them against a hardcoded `lb_ips` config list. This breaks every time the platform migrates load balancer IPs, requiring users to update their DNS A records. Switching to CNAME validation decouples users from the platform's IPs: users point their domain at `freepod.eu` once, and the platform can change its underlying IPs freely.

## What Changes

- **Remove** `lb_ips` from `CaelusSettings` and from Terraform — the IP list is no longer needed for validation
- **Add** `domain: str = ""` to `CaelusSettings` (populated from `CAELUS_DOMAIN`, sourced from Terraform's existing `var.domain`) as the required CNAME target
- **Replace** `_check_resolving()` (socket-based A-record lookup) with `_check_cname()` (explicit CNAME record query via `dnspython`)
- **Add** `dnspython` as a runtime dependency
- CNAME must point **exactly** to `freepod.eu` — no subdomains, no chain following
- Error reason stays `not_resolving` (no new error codes); no grace period for existing A-record users
- **Update** the UI error label for `not_resolving` to explain the CNAME requirement
- **Add** proactive CNAME instruction helper text in custom domain mode

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `hostname-validation`: DNS check changes from A-record/IP matching (`lb_ips`) to explicit CNAME record validation (`settings.domain`). The skip-when-unconfigured guard moves from `lb_ips == []` to `domain == ""`, and wildcard subdomains bypass the check entirely.
- `hostname-check-endpoint`: the "does not resolve" scenario re-described in terms of a missing/incorrect CNAME to `settings.domain` rather than A-record/LB-IP matching. Endpoint contract (returns `not_resolving`) is unchanged.
- `hostname-field-ui`: `not_resolving` error label updated to reflect CNAME requirement; custom mode adds static helper text instructing users to create a CNAME record pointing to `freepod.eu`.

## Impact

- **`api/pyproject.toml`** — add `dnspython` dependency
- **`api/app/config.py`** — remove `lb_ips`, add `domain: str = ""` (from `CAELUS_DOMAIN`)
- **`api/app/services/hostnames.py`** — replace `_check_resolving` with `_check_cname`
- **`api/tests/test_hostnames.py`** — update DNS test cases to mock `dns.resolver.resolve` instead of `socket.getaddrinfo`; remove tests for lb_ips skip behavior
- **`api/tests/test_config.py`** — remove `lb_ips` assertions (incl. `test_list_field_json_parsing`), add `domain` / `CAELUS_DOMAIN` assertions
- **`tf/app/caelus/configmap.tf`** — replace `CAELUS_LB_IPS` with `CAELUS_DOMAIN = var.domain`
- **`ui/src/components/HostnameField.tsx`** — update error label, add CNAME helper text
- **`tf/`** — remove `lb_ips` variable and all references
