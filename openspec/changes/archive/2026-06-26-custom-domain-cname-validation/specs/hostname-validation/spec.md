## MODIFIED Requirements

### Requirement: Hostname validation service exposes a single public function
The system MUST provide a hostname validation function `require_valid_hostname_for_deployment(session, fqdn)` in `api/app/services/hostnames.py` that validates whether a given FQDN can be used for a new Caelus deployment. The function MUST normalize the FQDN to lowercase before performing any checks. The function MUST return `None` on success or raise a `HostnameException` with a `reason` attribute on failure.

#### Scenario: Valid hostname passes all checks
- **WHEN** `require_valid_hostname_for_deployment` is called with a well-formed FQDN that is not reserved, not in use by any active deployment, and has a CNAME record pointing to `settings.domain`
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

#### Scenario: Hostname does not have a valid CNAME to the platform
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that has no CNAME record, or whose CNAME does not point exactly to `settings.domain`
- **THEN** the function raises `HostnameException` with `reason="not_resolving"`

#### Scenario: Hostname does not exist in DNS
- **WHEN** `require_valid_hostname_for_deployment` is called with an FQDN that has no DNS records at all
- **THEN** the function raises `HostnameException` with `reason="not_resolving"`

### Requirement: DNS check validates hostname CNAME points to domain
The DNS check MUST query the CNAME record for the given FQDN using the `dnspython` library. To avoid being misled by a recursive resolver's negative cache (a freshly created CNAME would otherwise be masked by a previously cached "no record" answer until its TTL expires), the check MUST query the FQDN zone's authoritative nameservers directly when they can be determined, and MAY fall back to the default system resolver only when the authoritative nameservers cannot be determined or reached. The resolved CNAME target (trailing dot stripped, lowercased) MUST equal `settings.domain` exactly. The check MUST be skipped when `settings.domain` is an empty string, or when the FQDN falls under any configured `wildcard_domain` (i.e. the platform manages those A records directly and they are not user-delegated). Any DNS error — including no CNAME record, wrong CNAME target, NXDOMAIN, or resolver timeout — MUST raise `HostnameException(reason="not_resolving")`.

#### Scenario: Freshly created CNAME is picked up without waiting for cache expiry
- **WHEN** an earlier check found no CNAME (a recursive resolver would cache that negative answer), the user then creates the correct CNAME, and the check runs again
- **THEN** the check queries the zone's authoritative nameservers directly and passes, without waiting for the recursive resolver's negative cache TTL to expire

#### Scenario: Authoritative nameservers unreachable falls back to system resolver
- **WHEN** the FQDN zone's authoritative nameservers cannot be determined or reached (e.g. outbound DNS is restricted)
- **THEN** the check falls back to the default system resolver, and a definitive resolver failure still raises `HostnameException(reason="not_resolving")`

#### Scenario: CNAME points exactly to domain
- **WHEN** the FQDN has a CNAME record whose target equals `settings.domain` (e.g. `"freepod.eu"`)
- **THEN** the DNS check passes

#### Scenario: CNAME points to a subdomain of domain
- **WHEN** the FQDN has a CNAME record whose target is a subdomain of `settings.domain` (e.g. `"ingress.freepod.eu"`)
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: FQDN has an A record but no CNAME
- **WHEN** the FQDN resolves via A/AAAA records but has no CNAME record
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: CNAME points to a different domain
- **WHEN** the FQDN has a CNAME record whose target is unrelated to `settings.domain`
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: FQDN does not exist in DNS
- **WHEN** DNS lookup for the FQDN returns NXDOMAIN
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: DNS resolver times out
- **WHEN** the DNS resolver raises a timeout exception
- **THEN** the function raises `HostnameException(reason="not_resolving")`

#### Scenario: DNS check skipped when domain is empty
- **WHEN** `require_valid_hostname_for_deployment` is called and `settings.domain` is an empty string
- **THEN** the DNS check is skipped and the hostname passes that check

#### Scenario: DNS check skipped for wildcard subdomain
- **WHEN** the FQDN is a subdomain of a configured `wildcard_domain` (e.g. `"foo.freepod.eu"` and `wildcard_domains` contains `"freepod.eu"`)
- **THEN** the DNS check is skipped and the hostname passes that check

## REMOVED Requirements

### Requirement: DNS resolution validates all resolved addresses against LB IPs
**Reason**: Replaced by CNAME-based validation. A-record IP matching is fragile when platform IPs change; CNAME delegation decouples users from platform IPs.
**Migration**: Replace `_check_resolving()` (socket-based) with `_check_cname()` (dnspython). Remove `lb_ips` from `CaelusSettings`. Add `domain: str = ""` to `CaelusSettings` (populated via `CAELUS_DOMAIN`).
