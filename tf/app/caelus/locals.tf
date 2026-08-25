locals {
  # PostgreSQL 18.6, supported to 2030-11-14 (design D14). Pinned to the patch
  # release rather than `18-alpine`: which version the tenant cluster runs is a
  # decision, not whatever a moving tag resolved to the day a pod restarted.
  tenant_db_image = "postgres:18.6-alpine"

  # PgBouncer >= 1.21 is a hard floor, not a preference: protocol-level prepared
  # statement support (`max_prepared_statements`) arrived there, and asyncpg,
  # SQLAlchemy, Prisma and node-postgres all use prepared statements by default.
  tenant_pooler_image = "edoburu/pgbouncer:v1.25.2-p0"
}
