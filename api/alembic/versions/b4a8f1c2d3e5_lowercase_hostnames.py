"""lowercase existing hostnames and add case-insensitive unique indexes

Revision ID: b4a8f1c2d3e5
Revises: a1b2c3d4e5f7
Create Date: 2026-03-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b4a8f1c2d3e5'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Detect case-variant duplicates among active (non-deleted) deployments.
    # If any exist, abort — an operator must resolve them manually before
    # this migration can proceed, because we cannot silently pick a winner.
    dupes = conn.execute(sa.text("""
        SELECT LOWER(hostname) AS lc, COUNT(*) AS cnt
        FROM deployment
        WHERE hostname IS NOT NULL
          AND status != 'deleted'
        GROUP BY LOWER(hostname)
        HAVING COUNT(*) > 1
    """)).fetchall()

    if dupes:
        detail = ", ".join(f"{row.lc} ({row.cnt}x)" for row in dupes)
        raise RuntimeError(
            f"Cannot normalize hostnames: case-variant duplicates exist "
            f"among active deployments: {detail}. "
            f"Resolve these manually before re-running the migration."
        )

    # Normalize all hostnames to lowercase.
    op.execute("UPDATE deployment SET hostname = LOWER(hostname) WHERE hostname != LOWER(hostname)")

    # Recreate unique indexes on LOWER(hostname) so the database enforces
    # case-insensitive uniqueness even if application-level normalization
    # is bypassed.
    op.drop_index("uq_hostname_active", table_name="deployment")
    op.drop_index("uq_deployment_active", table_name="deployment")

    op.create_index(
        "uq_hostname_active",
        "deployment",
        [sa.text("LOWER(hostname)")],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", sa.text("LOWER(hostname)"), "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )


def downgrade() -> None:
    # Restore raw-column indexes (original casing cannot be recovered).
    op.drop_index("uq_deployment_active", table_name="deployment")
    op.drop_index("uq_hostname_active", table_name="deployment")

    op.create_index(
        "uq_hostname_active",
        "deployment",
        ["hostname"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", "hostname", "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
