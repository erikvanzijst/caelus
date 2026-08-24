## REMOVED Requirements

### Requirement: Partial unique indexes MUST define backend parity
**Reason**: SQLite is no longer a supported backend, so there is no second
dialect to keep in parity with. A declaration carrying both predicates now
states a choice the system does not have.

**Migration**: Partial index predicates are declared for PostgreSQL only. See
the `postgres-only-persistence` capability, requirement "Partial index
predicates are declared for PostgreSQL only", which replaces this requirement.
Existing model declarations drop their `sqlite_where` keyword and keep
`postgresql_where` unchanged; already-applied Alembic revisions are left as
they are, because the keyword is inert against PostgreSQL.
