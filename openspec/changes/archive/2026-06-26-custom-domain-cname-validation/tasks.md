## 1. Dependencies

- [x] 1.1 Add `dnspython` to `api/pyproject.toml` dependencies

## 2. Config

- [x] 2.1 Remove `lb_ips: list[str] = []` from `CaelusSettings` in `api/app/config.py`
- [x] 2.2 Add `domain: str = ""` to `CaelusSettings` in `api/app/config.py` (populated via `CAELUS_DOMAIN` env var; empty string means CNAME validation is skipped)

## 3. Backend Service

- [x] 3.1 Replace `_check_resolving()` in `api/app/services/hostnames.py` with `_check_cname()` using `dns.resolver.resolve(fqdn, 'CNAME')`; target (trailing dot stripped, lowercased) must equal `settings.domain` exactly; skip when `settings.domain` is empty **or** when the FQDN falls under any `settings.wildcard_domains` entry — reuse the same suffix-match logic as `_check_wildcard_depth` (`fqdn == d or fqdn.endswith(f".{d}")`); catch `dns.exception.DNSException` (base class covering `NXDOMAIN`, `NoAnswer`, `NoNameservers`, `Timeout`) and raise `HostnameException(reason="not_resolving")`
- [x] 3.2 Update `require_valid_hostname_for_deployment()` to call `_check_cname()` instead of `_check_resolving()`

## 4. Backend Tests

- [x] 4.1 Update the `_settings()` helper in `api/tests/test_hostnames.py` (line ~35): remove `lb_ips` from its `defaults` dict — passing `lb_ips` to `CaelusSettings` after the field is removed raises a pydantic error and breaks *every* test in the file, not just the DNS ones. Update the import on line 15 from `_check_resolving` to `_check_cname`; drop the now-unused `socket` import
- [x] 4.2 Rewrite `TestCheckResolving` as `TestCheckCname`: mock `dns.resolver.resolve` instead of `socket.getaddrinfo`; cover exact-match passes, subdomain-of-domain fails, A-record-only (`NoAnswer`) fails, wrong target fails, NXDOMAIN fails, timeout fails, empty `domain` skips, wildcard subdomain skips (assert `dns.resolver.resolve` is **not called** at all)
- [x] 4.3 Update `TestRequireValidHostname`: replace every `lb_ips=[...]` override with `domain=...` (and add `wildcard_domains=...` + mocked CNAME for any passing custom-domain case)
- [x] 4.4 Update `TestHostnameCheckEndpoint.test_not_resolving` (line ~397): replace `_settings(lb_ips=["1.2.3.4"])` with `_settings(domain="freepod.eu")` and patch `dns.resolver.resolve` to raise, instead of patching `socket.getaddrinfo`
- [x] 4.5 Update `api/tests/test_config.py`: in `test_default_values` assert `settings.domain == ""` and drop the `lb_ips` assertion; fix `test_list_field_json_parsing` (sets `CAELUS_LB_IPS` / asserts `settings.lb_ips`, lines ~31/35) by removing that env var + assertion; add a `CAELUS_DOMAIN` env-loading assertion

## 5. Terraform

- [x] 5.1 Remove `lb_ips` variable from `tf/app/caelus/variables.tf`
- [x] 5.2 Remove `CAELUS_LB_IPS` from `tf/app/caelus/configmap.tf` and add `CAELUS_DOMAIN = var.domain` (already available in the module; resolves to `"freepod.eu"` in prod and `"dev.freepod.eu"` in dev automatically)

## 6. UI

- [x] 6.1 Update the `not_resolving` label in `REASON_LABELS` in `ui/src/components/HostnameField.tsx` to `"Create a CNAME record pointing to freepod.eu"`
- [x] 6.2 Add static helper text in custom FQDN mode (`HostnameField.tsx`) instructing users to create a CNAME record: "Point your domain at Freepod: create a CNAME record → freepod.eu"
