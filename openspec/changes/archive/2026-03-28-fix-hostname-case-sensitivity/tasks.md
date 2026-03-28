## 1. Hostname Normalization

- [x] 1.1 Add `fqdn = fqdn.lower()` at the top of `require_valid_hostname_for_deployment()` in `api/app/services/hostnames.py`, before any validation checks run
- [x] 1.2 Lowercase the return value of `_derive_hostname()` in `api/app/services/deployments.py` so stored hostnames are always canonical lowercase

## 2. Tests

- [x] 2.1 Add test case in `api/tests/test_hostnames.py` verifying that a mixed-case FQDN is detected as in-use when the lowercase variant exists in the database
- [x] 2.2 Add test case verifying that reserved hostname matching is case-insensitive (e.g., `SMTP.app.deprutser.be` is rejected when `smtp.app.deprutser.be` is reserved)
- [x] 2.3 Add test case verifying the API endpoint returns the normalized (lowercased) FQDN in the response body
- [x] 2.4 Run the full hostname test suite and confirm all tests pass
