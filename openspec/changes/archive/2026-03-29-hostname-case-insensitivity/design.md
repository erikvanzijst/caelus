## Context

The hostname validation service (`api/app/services/hostnames.py`) checks if a hostname is already in use by querying the database with a case-sensitive string comparison. The `DeploymentORM.hostname` column uses SQLAlchemy's `String()` type, which is case-sensitive by default in both SQLite and PostgreSQL. DNS resolution is case-insensitive per RFC 1035, so this mismatch allows logically duplicate hostnames.

## Goals / Non-Goals

**Goals:**
- Make hostname availability checks case-insensitive
- Normalize all stored hostnames to lowercase
- Prevent future case-based duplicates at the database level
- Deduplicate existing data if conflicts exist

**Non-Goals:**
- Changing hostname format validation (RFC 952/1123 compliance remains unchanged)
- Modifying the API contract (endpoint signature stays the same)
- Supporting case-preservation for display purposes

## Decisions

### 1. Normalize hostnames to lowercase on input

**Decision**: Convert hostnames to lowercase in `_check_available()` and during deployment creation/update.

**Rationale**: 
- DNS is case-insensitive; lowercase normalization is the standard approach
- Simpler than implementing case-insensitive collation everywhere
- Matches common practice (e.g., email addresses, domain names)

**Alternatives considered**:
- Case-insensitive collation only: More complex, database-specific, doesn't prevent storage of duplicates
- Store both original and lowercase: Unnecessary complexity; hostname case has no semantic meaning

### 2. Database-level enforcement with `LOWER()` expression

**Decision**: Use a functional unique index on `LOWER(hostname)` for PostgreSQL and SQLite.

**Rationale**:
- Enforces uniqueness at the database level, not just in application code
- PostgreSQL supports `CREATE UNIQUE INDEX ... WHERE lower(column) = ...`
- SQLite supports expression indexes with `LOWER()`
- More portable than database-specific collation settings

**Alternatives considered**:
- `COLLATE NOCASE` (SQLite) / `COLLATE CI` (PostgreSQL): Less portable, collation behavior varies
- Trigger-based enforcement: More complex, harder to maintain

### 3. Data migration to lowercase + conflict resolution

**Decision**: Create an Alembic migration that:
1. Converts all existing hostnames to lowercase
2. Detects and reports any case-only duplicates before applying
3. Allows manual intervention if conflicts are found

**Rationale**:
- Safe rollback path if conflicts are discovered
- Transparent to users (DNS behavior doesn't change)
- One-time cost during deployment

**Alternatives considered**:
- Silent deduplication: Risk of unexpected data loss
- Reject mixed-case hostnames without migration: Breaks existing deployments

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Existing case-only duplicates cause migration failure | Migration includes pre-check that reports conflicts; manual resolution before applying |
| Application code assumes hostname case is preserved | Search codebase for hostname string comparisons; all should use lowercase now |
| External systems expect mixed-case hostnames | DNS is case-insensitive; no external system should depend on case |
| Rollback requires reversing hostname normalization | Document rollback migration; test in staging first |

## Migration Plan

1. **Pre-deployment check**: Run a query to detect case-only duplicates
   ```sql
   SELECT LOWER(hostname) as h, COUNT(*) 
   FROM deployment 
   WHERE status != 'deleted' 
   GROUP BY h 
   HAVING COUNT(*) > 1;
   ```

2. **Apply migration**:
   - Step 1: Normalize all hostnames to lowercase
   - Step 2: Drop old unique index
   - Step 3: Create new functional index on `LOWER(hostname)`

3. **Deploy application code**: Update `hostnames.py` to lowercase before comparison

4. **Rollback**: Reverse migration steps if needed

## Open Questions

- Should we add a CHECK constraint to reject mixed-case hostnames on insert, or just normalize silently?
  - Recommendation: Normalize silently for backward compatibility