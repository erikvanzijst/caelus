## 1. Backend — Wildcard Depth Validation

- [ ] 1.1 Add `_check_wildcard_depth(fqdn, settings)` function to `api/app/services/hostnames.py` that raises `HostnameException("nested_subdomain")` when the FQDN has a multi-level prefix under a configured wildcard domain, or when the FQDN exactly matches a wildcard domain (no prefix)
- [ ] 1.2 Insert `_check_wildcard_depth` call in `require_valid_hostname_for_deployment` between `_check_format` and `_check_reserved`
- [ ] 1.3 Add tests for `_check_wildcard_depth`: single-level prefix passes, multi-level prefix rejected, bare wildcard domain rejected, non-wildcard FQDN skipped, case-insensitive matching

## 2. Frontend — Prefix Input Restriction

- [ ] 2.1 In `HostnameField.tsx`, strip dot characters from the prefix `onChange` handler in wildcard mode (e.g. `e.target.value.replace(/\./g, '')`)
- [ ] 2.2 Add `nested_subdomain: 'Only a single subdomain level is allowed'` to `REASON_LABELS` in `HostnameField.tsx`
- [ ] 2.3 Add frontend tests for dot stripping and the new reason label
