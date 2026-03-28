## MODIFIED Requirements

### Requirement: Hostname validation service exposes a single public function
The system MUST provide a hostname validation function `require_valid_hostname_for_deployment(session, fqdn)` in `api/app/services/hostnames.py` that validates whether a given FQDN can be used for a new Caelus deployment. The function MUST normalize the FQDN to lowercase before performing any checks. The function MUST return `None` on success or raise a `HostnameException` with a `reason` attribute on failure.

#### Scenario: Valid hostname passes all checks
- **WHEN** `require_valid_hostname_for_deployment` is called with a well-formed FQDN that is not reserved, not in use by any active deployment, and resolves to configured LB IPs
- **THEN** the function returns `None`

#### Scenario: Mixed-case hostname is normalized before checks
- **WHEN** `require_valid_hostname_for_deployment` is called with `"Foo.Dev.Deprutser.Be"`
- **THEN** the function normalizes the FQDN to `"foo.dev.deprutser.be"` before running format, reserved, availability, and DNS checks

#### Scenario: Mixed-case hostname detected as in use
- **WHEN** `require_valid_hostname_for_deployment` is called with `"FOO.dev.deprutser.be"` and an active deployment has hostname `"foo.dev.deprutser.be"`
- **THEN** the function raises `HostnameException` with `reason="in_use"`

#### Scenario: Invalid hostname format
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that does not conform to RFC 952/1123 (e.g., exceeds 253 characters, contains invalid characters, has labels longer than 63 characters, or has labels with leading/trailing hyphens)
- **THEN** the function raises `HostnameException` with `reason="invalid"`

#### Scenario: Reserved hostname matched case-insensitively
- **WHEN** `require_valid_hostname_for_deployment` is called with `"SMTP.app.deprutser.be"` and `"smtp.app.deprutser.be"` is in the `reserved_hostnames` setting
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

## ADDED Requirements

### Requirement: Derived hostnames are normalized to lowercase before storage
The `_derive_hostname()` function in `api/app/services/deployments.py` MUST return hostnames in lowercase form. This ensures the `DeploymentORM.hostname` column always stores the canonical lowercase representation.

#### Scenario: Mixed-case hostname from user values is lowercased
- **WHEN** a deployment is created with user values containing hostname `"MyApp.Dev.Deprutser.Be"`
- **THEN** the derived hostname stored on the deployment record is `"myapp.dev.deprutser.be"`

#### Scenario: Lowercase hostname from user values is unchanged
- **WHEN** a deployment is created with user values containing hostname `"myapp.dev.deprutser.be"`
- **THEN** the derived hostname stored on the deployment record is `"myapp.dev.deprutser.be"`
