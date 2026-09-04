"""make deployment.namespace globally unique

Revision ID: a9b0c1d2e3f4
Revises: e7f8a9b0c1d2
Create Date: 2026-09-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE UNIQUE INDEX on violating data names the index, not the rows. The
    # namespace is a live Kubernetes namespace, so an operator hitting this
    # needs to know which ones to look at.
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT namespace, count(*) AS n FROM deployment "
            "GROUP BY namespace HAVING count(*) > 1 ORDER BY n DESC, namespace"
        )
    ).all()
    if duplicates:
        listed = ", ".join(f"{ns} ({n} rows)" for ns, n in duplicates)
        raise RuntimeError(
            "deployment.namespace cannot be made unique: duplicates exist: " + listed
        )

    op.create_index("uq_deployment_namespace", "deployment", ["namespace"], unique=True)
    # Subsumed: one row per namespace makes a duplicate (namespace, name) pair
    # unreachable.
    op.drop_index("uq_deployment_ns_name_active", table_name="deployment")


def downgrade() -> None:
    op.create_index(
        "uq_deployment_ns_name_active",
        "deployment",
        ["namespace", "name"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
        sqlite_where=sa.text("status != 'deleted'"),
    )
    op.drop_index("uq_deployment_namespace", table_name="deployment")
