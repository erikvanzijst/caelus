## MODIFIED Requirements

### Requirement: Validation checks execute in order and short-circuit on first failure
The hostname validation MUST execute checks in the following order: format, wildcard depth, reserved, availability, DNS resolution. The function MUST short-circuit and raise on the first failing check.

#### Scenario: Reserved hostname skips availability and DNS checks
- **WHEN** an FQDN is well-formed, passes wildcard depth check, but appears in the reserved hostnames list
- **THEN** the function raises `HostnameException(reason="reserved")` without querying the database or performing DNS resolution

#### Scenario: Unavailable hostname skips DNS check
- **WHEN** an FQDN is well-formed, passes wildcard depth check, not reserved, but already in use
- **THEN** the function raises `HostnameException(reason="in_use")` without performing DNS resolution

#### Scenario: Nested subdomain under wildcard domain skips reserved, availability, and DNS checks
- **WHEN** an FQDN is well-formed but has a multi-level prefix under a configured wildcard domain
- **THEN** the function raises `HostnameException(reason="nested_subdomain")` without checking reserved hostnames, querying the database, or performing DNS resolution

### Requirement: HostnameException carries a reason attribute
The `HostnameException` class in `api/app/services/errors.py` MUST have a `reason` attribute of type `str`. Valid reason values MUST be: `"invalid"`, `"reserved"`, `"in_use"`, `"not_resolving"`, `"nested_subdomain"`.

#### Scenario: Exception reason is accessible
- **WHEN** a `HostnameException` is raised with `reason="nested_subdomain"`
- **THEN** the exception's `reason` attribute equals `"nested_subdomain"`

## ADDED Requirements

### Requirement: Wildcard depth check rejects multi-level prefixes under configured wildcard domains
The hostname validation MUST check whether the submitted FQDN falls under a configured wildcard domain. If it does, the prefix (the portion before the wildcard domain suffix) MUST be exactly one DNS label (no dots). If the prefix contains dots, the function MUST raise `HostnameException(reason="nested_subdomain")`. FQDNs that do not match any wildcard domain MUST skip this check.

#### Scenario: Single-level prefix under wildcard domain passes
- **WHEN** `require_valid_hostname_for_deployment` is called with `"myapp.dev.deprutser.be"` and `wildcard_domains` contains `"dev.deprutser.be"`
- **THEN** the wildcard depth check passes and validation continues to the next check

#### Scenario: Multi-level prefix under wildcard domain is rejected
- **WHEN** `require_valid_hostname_for_deployment` is called with `"foo.bar.dev.deprutser.be"` and `wildcard_domains` contains `"dev.deprutser.be"`
- **THEN** the function raises `HostnameException(reason="nested_subdomain")`

#### Scenario: Bare wildcard domain with no prefix is rejected
- **WHEN** `require_valid_hostname_for_deployment` is called with `"dev.deprutser.be"` and `wildcard_domains` contains `"dev.deprutser.be"`
- **THEN** the function raises `HostnameException(reason="nested_subdomain")`

#### Scenario: FQDN not under any wildcard domain skips check
- **WHEN** `require_valid_hostname_for_deployment` is called with `"foo.bar.example.com"` and `wildcard_domains` contains `"dev.deprutser.be"`
- **THEN** the wildcard depth check is skipped and validation continues to the next check

#### Scenario: Multi-level prefix check is case-insensitive
- **WHEN** `require_valid_hostname_for_deployment` is called with `"Foo.Bar.Dev.Deprutser.Be"` and `wildcard_domains` contains `"dev.deprutser.be"`
- **THEN** after lowercase normalization, the function raises `HostnameException(reason="nested_subdomain")` because `foo.bar` is a multi-level prefix
