## Why

DNS hostnames are case-insensitive per RFC 4343, but the `/api/hostnames/{fqdn}` endpoint and the hostname validation service compare hostnames using exact (case-sensitive) string matching. This means `Foo.dev.deprutser.be` is incorrectly reported as available even when `foo.dev.deprutser.be` is already in use by an active deployment. A user could then create a conflicting deployment, leading to routing ambiguity or silent overwrites.

## What Changes

- Normalize hostnames to lowercase before all validation checks (format, reserved, availability, DNS resolution).
- Apply the same normalization when storing hostnames on deployment records, ensuring the database uniqueness constraint operates on canonical form.
- Update the reserved-hostname comparison to be case-insensitive.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `hostname-validation`: The validation service must normalize the FQDN to lowercase before performing any checks (format, reserved, availability, DNS), and all comparisons must be case-insensitive.
- `hostname-check-endpoint`: The endpoint must return the normalized (lowercased) FQDN in its response, reflecting the canonical form that will be stored.

## Impact

- **Code**: `api/app/services/hostnames.py` (normalization + comparison logic), `api/app/services/deployments.py` (hostname derivation/storage), `api/app/api/hostnames.py` (endpoint).
- **Database**: Existing hostnames with mixed case should be considered for a data migration to lowercase. The partial unique index `uq_hostname_active` already enforces uniqueness but operates on the raw stored value — normalizing on write makes it effective for case variants.
- **Tests**: `api/tests/test_hostnames.py` needs new cases covering mixed-case inputs.
- **API**: The response `fqdn` field may now differ from the request path parameter (lowercased). This is a minor behavioral change for API consumers.
