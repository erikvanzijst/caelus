## ADDED Requirements

### Requirement: Centralized configuration via Pydantic BaseSettings
The system MUST provide a `CaelusSettings` class in `api/app/config.py` using Pydantic `BaseSettings` with `env_prefix="CAELUS_"`. All application configuration MUST be read through this class.

#### Scenario: Settings loaded from environment variables
- **WHEN** the application starts with `CAELUS_DATABASE_URL=postgresql://...` and `CAELUS_LOG_LEVEL=DEBUG` set
- **THEN** `get_settings().database_url` returns the database URL and `get_settings().log_level` returns `"DEBUG"`

#### Scenario: Default values applied when env vars are absent
- **WHEN** the application starts without `CAELUS_LOG_LEVEL` set
- **THEN** `get_settings().log_level` returns `"INFO"`

### Requirement: Settings instance is cached via get_settings()
The system MUST provide a `get_settings()` function that returns a cached `CaelusSettings` instance (via `@lru_cache` or equivalent). The same instance MUST be returned on repeated calls.

#### Scenario: Cached settings
- **WHEN** `get_settings()` is called twice
- **THEN** both calls return the same object instance

### Requirement: All env vars use CAELUS_ prefix
All environment variable names MUST use the `CAELUS_` prefix. The previous unprefixed env var names (`DATABASE_URL`, `STATIC_PATH`) MUST NOT be supported.

#### Scenario: Legacy DATABASE_URL env var is not read
- **WHEN** the application starts with `DATABASE_URL=postgresql://old` set but `CAELUS_DATABASE_URL` is not set
- **THEN** the settings use the default database URL, not the value from `DATABASE_URL`

### Requirement: Settings includes hostname-related configuration fields
The `CaelusSettings` class MUST include the following fields with their default values:
- `lb_ips: list[str] = []` — IPv4 and IPv6 addresses of Caelus' load balancer
- `wildcard_domains: list[str] = []` — Caelus-provided wildcard domain suffixes
- `reserved_hostnames: list[str] = []` — Blacklisted hostnames

#### Scenario: LB IPs configured via JSON env var
- **WHEN** `CAELUS_LB_IPS='["1.2.3.4","2001:db8::1"]'` is set
- **THEN** `get_settings().lb_ips` returns `["1.2.3.4", "2001:db8::1"]`

#### Scenario: Hostname-related fields default to empty lists
- **WHEN** none of `CAELUS_LB_IPS`, `CAELUS_WILDCARD_DOMAINS`, or `CAELUS_RESERVED_HOSTNAMES` are set
- **THEN** all three fields default to empty lists

### Requirement: Existing config consumers are migrated
All existing code that reads `DATABASE_URL`, `STATIC_PATH`, or `CAELUS_LOG_LEVEL` directly from `os.environ` MUST be updated to use the `CaelusSettings` instance. This includes `db.py`, `logging_config.py`, and `main.py`.

#### Scenario: Database engine uses settings
- **WHEN** the database engine is initialized
- **THEN** it reads the connection URL from `get_settings().database_url`

#### Scenario: Static path uses settings
- **WHEN** the static file path is determined
- **THEN** it reads from `get_settings().static_path`
