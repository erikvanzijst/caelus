# hostname-validation Specification

## Purpose
Validate hostnames for Caelus deployments with case-insensitive uniqueness and lowercase normalization.
## Requirements
### Requirement: Hostname validation service exposes a single public function
The system MUST provide a hostname validation function `require_valid_hostname_for_deployment(session, fqdn)` in `api/app/services/hostnames.py` that validates whether a given FQDN can be used for a new Caelus deployment. The function MUST return `None` on success or raise a `HostnameException` with a `reason` attribute on failure.

#### Scenario: Valid hostname passes all checks
- **WHEN** `require_valid_hostname_for_deployment` is called with a well-formed FQDN that is not reserved, not in use by any active deployment, and resolves to configured LB IPs
- **THEN** the function returns `None`

#### Scenario: Invalid hostname format
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that does not conform to RFC 952/1123 (e.g., exceeds 253 characters, contains invalid characters, has labels longer than 63 characters, or has labels with leading/trailing hyphens)
- **THEN** the function raises `HostnameException` with `reason="invalid"`

#### Scenario: Reserved hostname
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that appears in the `reserved_hostnames` setting
- **THEN** the function raises `HostnameException` with `reason="reserved"`

#### Scenario: Hostname already in use
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that is the `hostname` of an active deployment (status not `deleted`)
- **THEN** the function raises `HostnameException` with `reason="in_use"`

#### Scenario: Hostname does not resolve to Caelus load balancer
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN whose resolved A/AAAA records are not all within the configured `lb_ips` set
- **THEN** the function raises `HostnameException` with `reason="not_resolving"`

#### Scenario: Hostname does not resolve at all
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that has no A or AAAA DNS records
- **THEN** the function raises `HostnameException` with `reason="not_resolving"`

#### Scenario: DNS check skipped when lb_ips is empty
- **WHEN** `require_valid_hostname_for_deployment` is called and `settings.lb_ips` is an empty list
- **THEN** the DNS resolution check is skipped and the hostname passes that check

### Requirement: Validation checks execute in order and short-circuit on first failure
The hostname validation MUST execute checks in the following order: format, reserved, availability, DNS resolution. The function MUST short-circuit and raise on the first failing check.

#### Scenario: Reserved hostname skips availability and DNS checks
- **WHEN** an FQDN is well-formed but appears in the reserved hostnames list
- **THEN** the function raises `HostnameException(reason="reserved")` without querying the database or performing DNS resolution

#### Scenario: Unavailable hostname skips DNS check
- **WHEN** an FQDN is well-formed, not reserved, but already in use
- **THEN** the function raises `HostnameException(reason="in_use")` without performing DNS resolution

### Requirement: HostnameException carries a reason attribute
The `HostnameException` class in `api/app/services/errors.py` MUST have a `reason` attribute of type `str`. Valid reason values MUST be: `"invalid"`, `"reserved"`, `"in_use"`, `"not_resolving"`.

#### Scenario: Exception reason is accessible
- **WHEN** a `HostnameException` is raised with `reason="in_use"`
- **THEN** the exception's `reason` attribute equals `"in_use"`

### Requirement: DNS resolution validates all resolved addresses against LB IPs
The DNS resolution check MUST resolve the FQDN using `socket.getaddrinfo()` (which follows CNAME chains), collect all unique IPv4 and IPv6 addresses, and verify that every resolved address is a member of the configured `lb_ips` set. A hostname that resolves to any address outside the `lb_ips` set MUST fail.

#### Scenario: Hostname resolves to only Caelus LB IPs
- **WHEN** an FQDN resolves to `1.2.3.4` and `2001:db8::1`, and `lb_ips` contains both
- **THEN** the DNS check passes

#### Scenario: Hostname resolves to a mix of Caelus and non-Caelus IPs
- **WHEN** an FQDN resolves to `1.2.3.4` (in `lb_ips`) and `9.9.9.9` (not in `lb_ips`)
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: Hostname resolves to only IPv4 when lb_ips has both v4 and v6
- **WHEN** an FQDN resolves to `1.2.3.4` only, and `lb_ips` contains `["1.2.3.4", "2001:db8::1"]`
- **THEN** the DNS check passes (IPv4-only is acceptable)

### Requirement: Hostname availability check is case-insensitive
The system MUST perform hostname availability checks in a case-insensitive manner. When checking if a hostname is already in use, the validation function `require_valid_hostname_for_deployment(session, fqdn)` MUST normalize the FQDN to lowercase before querying the database. A hostname that differs only in case from an existing deployment's hostname (e.g., `Foo.dev.deprutser.be` vs `foo.dev.deprutser.be`) MUST be treated as in-use and raise `HostnameException` with `reason="in_use"`.

#### Scenario: Case-different hostname is rejected as in-use
- **WHEN** `require_valid_hostname_for_deployment` is called with `Foo.dev.deprutser.be`
- **AND** a deployment exists with hostname `foo.dev.deprutser.be` (all lowercase)
- **THEN** the function raises `HostnameException` with `reason="in_use"`

#### Scenario: Same hostname with different case raises in_use
- **WHEN** `require_valid_hostname_for_deployment` is called with `TEST.EXAMPLE.COM`
- **AND** a deployment exists with hostname `test.example.com`
- **THEN** the function raises `HostnameException` with `reason="in_use"`

#### Scenario: Mixed-case update to same hostname (normalized) succeeds
- **WHEN** updating an existing deployment that currently has hostname `test.example.com`
- **AND** the update request specifies hostname `TEST.EXAMPLE.COM`
- **THEN** the hostname is normalized to lowercase and the update succeeds (no self-conflict)

### Requirement: Hostnames are normalized to lowercase on storage
The system MUST normalize all hostnames to lowercase before storing them in the `deployment` table. When a deployment is created or updated with a hostname, the hostname MUST be converted to lowercase in the database.

#### Scenario: Deployment creation normalizes hostname
- **WHEN** a deployment is created with hostname `MyApp.Example.Com`
- **THEN** the hostname is stored as `myapp.example.com` in the database

#### Scenario: Deployment update normalizes hostname
- **WHEN** a deployment's hostname is updated from `old.example.com` to `New.Example.Com`
- **THEN** the new hostname is stored as `new.example.com` in the database

### Requirement: Database enforces case-insensitive uniqueness
The `deployment` table MUST enforce a unique constraint on hostnames that is case-insensitive. The database MUST reject any attempt to insert or update a deployment with a hostname that matches an existing active deployment's hostname when compared case-insensitively.

#### Scenario: Duplicate hostname with different case is rejected at database level
- **WHEN** an attempt is made to insert a deployment with hostname `Test.Example.Com`
- **AND** a deployment already exists with hostname `test.example.com` (status != deleted)
- **THEN** the database raises a unique constraint violation

### Requirement: Hostname validation service normalizes before checking
The `_check_available(session, fqdn, exclude_deployment_id)` function in `api/app/services/hostnames.py` MUST normalize the `fqdn` parameter to lowercase before constructing the database query. The query MUST compare against lowercase hostnames in the database.

#### Scenario: Lowercase normalization happens before DB query
- **WHEN** `_check_available` is called with `Mixed.Case.Example.Com`
- **THEN** the SQL query uses `lowercase` form `mixed.case.example.com` for comparison
