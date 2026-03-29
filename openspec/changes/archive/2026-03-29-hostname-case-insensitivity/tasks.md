## 1. Service Layer Changes

- [x] 1.1 Update `_check_available()` in `api/app/services/hostnames.py` to normalize `fqdn` to lowercase before database query
- [x] 1.2 Add lowercase normalization in `require_valid_hostname_for_deployment()` before calling `_check_available()`
- [x] 1.3 Update `_check_reserved()` to use lowercase comparison if needed
- [x] 1.4 Write unit tests for case-insensitive hostname checks in `api/tests/test_hostnames.py`

## 4. API Endpoint Verification

- [x] 4.1 Verify `/api/hostnames/{fqdn}` endpoint returns correct "in_use" for case variants
- [x] 4.2 Add API integration test for case-insensitive hostname check
- [x] 4.3 Verify response format unchanged (fqdn, usable, reason fields)

## 5. Tests

- [x] 5.1 Add test: Case-different hostname should be rejected as in_use
- [x] 5.2 Add test: Mixed-case update to same hostname should succeed
- [x] 5.3 Add test: Deployment creation with mixed-case stores lowercase
- [x] 5.4 Add test: Database unique constraint rejects case variants
- [x] 5.5 Run existing hostname tests to ensure no regression

## 6. Documentation

- [x] 6.1 Update `api/README.md` if hostname behavior documentation needs changes
- [x] 6.2 Add migration runbook notes for production deployment