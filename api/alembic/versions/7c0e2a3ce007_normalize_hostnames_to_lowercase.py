"""normalize_hostnames_to_lowercase

Revision ID: 7c0e2a3ce007
Revises: a1b2c3d4e5f7
Create Date: 2026-03-28 14:55:04.053883

"""

from alembic import op
import sqlalchemy as sa


revision = "7c0e2a3ce007"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Check for case-only duplicates before migration
    # This query finds any active hostnames that would conflict after normalization
    conn = op.get_bind()

    # Run duplicate check - report but don't fail (works for both PostgreSQL and SQLite)
    result = conn.execute(
        sa.text("""
        SELECT LOWER(hostname) as h, COUNT(*) 
        FROM deployment 
        WHERE status != 'deleted' 
        GROUP BY h 
        HAVING COUNT(*) > 1;
    """)
    )
    duplicates = result.fetchall()
    if duplicates:
        print("WARNING: Case-only duplicates detected:")
        for row in duplicates:
            print(f"  - {row[0]}: {row[1]} deployments")
        print("Manual resolution required before proceeding.")

    # Step 2: Normalize all hostnames to lowercase
    op.execute(sa.text("UPDATE deployment SET hostname = LOWER(hostname)"))

    # Step 3: Drop old unique indexes
    op.drop_index("uq_hostname_active", table_name="deployment")
    op.drop_index("uq_deployment_active", table_name="deployment")

    # Step 4: Create new functional unique indexes on LOWER(hostname)
    # PostgreSQL
    if conn.dialect.name == "postgresql":
        op.create_index(
            "uq_hostname_active",
            "deployment",
            [sa.text("LOWER(hostname)")],
            unique=True,
            postgresql_where=sa.text("status <> 'deleted'"),
        )
        op.create_index(
            "uq_deployment_active",
            "deployment",
            ["user_id", sa.text("LOWER(hostname)"), "desired_template_id"],
            unique=True,
            postgresql_where=sa.text("status <> 'deleted'"),
        )
    else:
        # SQLite - use LOWER() in the index expression
        op.create_index(
            "uq_hostname_active",
            "deployment",
            [sa.text("LOWER(hostname)")],
            unique=True,
            sqlite_where=sa.text("status != 'deleted'"),
        )
        op.create_index(
            "uq_deployment_active",
            "deployment",
            ["user_id", sa.text("LOWER(hostname)"), "desired_template_id"],
            unique=True,
            sqlite_where=sa.text("status != 'deleted'"),
        )


def downgrade() -> None:
    # Step 1: Drop new functional indexes (no where clause needed for drop)
    op.drop_index("uq_deployment_active", table_name="deployment")
    op.drop_index("uq_hostname_active", table_name="deployment")

    # Step 2: Recreate old case-sensitive indexes
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.create_index(
            "uq_hostname_active",
            "deployment",
            ["hostname"],
            unique=True,
            postgresql_where=sa.text("status <> 'deleted'"),
        )
        op.create_index(
            "uq_deployment_active",
            "deployment",
            ["user_id", "hostname", "desired_template_id"],
            unique=True,
            postgresql_where=sa.text("status <> 'deleted'"),
        )
    else:
        op.create_index(
            "uq_hostname_active",
            "deployment",
            ["hostname"],
            unique=True,
            sqlite_where=sa.text("status != 'deleted'"),
        )
        op.create_index(
            "uq_deployment_active",
            "deployment",
            ["user_id", "hostname", "desired_template_id"],
            unique=True,
            sqlite_where=sa.text("status != 'deleted'"),
        )
