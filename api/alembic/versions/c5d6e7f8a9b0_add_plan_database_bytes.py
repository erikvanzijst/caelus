"""add plan_template_version.database_bytes

The relational-database allowance for a deployment. It is a separate column
rather than a reinterpretation of `storage_bytes`, which already carries two
meanings -- the Garage bucket quota and the chart's PVC size -- and cannot
take a third.

Nullable and purely additive: existing template versions declare no database
allowance, which is exactly what "no relational storage" means. Rolling back
drops the column; nothing references it.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plan_template_version",
        sa.Column("database_bytes", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("plan_template_version", "database_bytes")
