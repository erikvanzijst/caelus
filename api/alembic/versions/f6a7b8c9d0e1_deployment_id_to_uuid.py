"""change deployment.id from integer sequence to uuid

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add temp UUID columns
    op.add_column("deployment", sa.Column("new_id", sa.Uuid(), nullable=True))
    op.add_column("deployment_reconcile_job", sa.Column("new_deployment_id", sa.Uuid(), nullable=True))

    # 2. Populate deployment.new_id with random UUIDs
    op.execute("UPDATE deployment SET new_id = gen_random_uuid()")

    # 3. Backfill the FK side to preserve relationships
    op.execute(
        "UPDATE deployment_reconcile_job j "
        "SET new_deployment_id = d.new_id "
        "FROM deployment d "
        "WHERE j.deployment_id = d.id"
    )

    # 4. Drop FK constraint, indexes, and PK
    op.drop_constraint(
        "deployment_reconcile_job_deployment_id_fkey",
        "deployment_reconcile_job",
        type_="foreignkey",
    )
    op.drop_index("ix_deployment_reconcile_job_deployment_id", table_name="deployment_reconcile_job")
    # Note: uq_open_reconcile_job_per_deployment does not exist in PostgreSQL
    # (defined in the ORM model but never migrated). We create it at the end
    # of this migration to bring PostgreSQL in sync with the model.

    # 5. Drop old columns and rename new ones
    op.drop_column("deployment_reconcile_job", "deployment_id")
    op.alter_column(
        "deployment_reconcile_job",
        "new_deployment_id",
        new_column_name="deployment_id",
        nullable=False,
    )

    # Drop deployment PK and old id column, rename new_id
    op.execute("ALTER TABLE deployment DROP CONSTRAINT deployment_pkey")
    op.drop_column("deployment", "id")
    op.alter_column("deployment", "new_id", new_column_name="id", nullable=False)

    # 6. Recreate PK, FK, and indexes
    op.create_primary_key("deployment_pkey", "deployment", ["id"])
    op.create_index(
        "ix_deployment_reconcile_job_deployment_id",
        "deployment_reconcile_job",
        ["deployment_id"],
    )
    op.create_foreign_key(
        "deployment_reconcile_job_deployment_id_fkey",
        "deployment_reconcile_job",
        "deployment",
        ["deployment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_open_reconcile_job_per_deployment",
        "deployment_reconcile_job",
        ["deployment_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade from UUID to integer deployment IDs is not supported. "
        "Restore from backup if needed."
    )
