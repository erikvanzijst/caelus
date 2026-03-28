## Context

The hostname validation service (`api/app/services/hostnames.py`) runs four sequential checks — format, reserved, availability, and DNS resolution — all using the raw FQDN string as-is. The database query in `_check_available` compares `DeploymentORM.hostname == fqdn` which is case-sensitive at the application layer (SQLAlchemy generates a `=` comparison; SQLite is case-insensitive by default for ASCII, but PostgreSQL is not). The partial unique index `uq_hostname_active` similarly operates on the stored value verbatim.

DNS is case-insensitive per RFC 4343. Users reasonably expect `Foo.example.com` and `foo.example.com` to refer to the same host. The current implementation does not enforce this.

## Goals / Non-Goals

**Goals:**
- Ensure all hostname comparisons (availability, reserved, uniqueness) are case-insensitive.
- Normalize hostnames to lowercase at the earliest entry point so downstream logic never sees mixed case.
- Keep the fix minimal and contained within the existing validation and storage paths.

**Non-Goals:**
- Internationalized domain names (IDN / punycode) — out of scope, not currently supported.
- Database-level collation changes — unnecessary if we normalize on write.
- Migrating existing mixed-case data — existing deployments are unlikely to have uppercase hostnames since browsers and DNS tools lowercase by convention, but a one-time migration could be done separately if needed.

## Decisions

### 1. Normalize early in `require_valid_hostname_for_deployment`

**Decision**: Call `fqdn = fqdn.lower()` at the top of `require_valid_hostname_for_deployment()` before any checks run.

**Rationale**: This is the single public entry point for all hostname validation (used by the API endpoint, deployment creation, and deployment updates). Normalizing here ensures every downstream check — format, reserved, availability, DNS — operates on the canonical lowercase form. No need to modify each individual check function.

**Alternative considered**: Normalizing in each `_check_*` function individually. Rejected because it duplicates logic and risks missing a path.

### 2. Normalize in `_derive_hostname` for storage

**Decision**: Also lowercase the return value of `_derive_hostname()` in `api/app/services/deployments.py` so the `DeploymentORM.hostname` column always stores lowercase.

**Rationale**: This ensures the database uniqueness constraint `uq_hostname_active` catches case-variant duplicates, and the availability query matches correctly even on case-sensitive databases like PostgreSQL.

### 3. Lowercase in the API endpoint response

**Decision**: The `HostnameCheck.fqdn` response field will contain the normalized (lowercased) FQDN, not the raw input.

**Rationale**: This signals to API consumers the canonical form that will be stored. The endpoint already passes the FQDN through `require_valid_hostname_for_deployment`, so the normalized value naturally flows to the response.

### 4. No database migration for existing data

**Decision**: Skip a data migration for now.

**Rationale**: Hostnames entered via browsers and DNS tooling are conventionally lowercase. The risk of existing mixed-case data is very low. If needed later, a simple `UPDATE deployment SET hostname = LOWER(hostname)` migration can be added.

## Risks / Trade-offs

- **API behavioral change**: Clients sending `GET /api/hostnames/Foo.Example.Com` will receive `fqdn: "foo.example.com"` in the response instead of the original casing. → Low risk; hostname casing is not semantically meaningful.
- **Existing mixed-case data**: If any existing deployment has an uppercase hostname, the new code will not retroactively fix it, potentially allowing a lowercase duplicate. → Mitigated by the low probability and the option to add a migration later.
