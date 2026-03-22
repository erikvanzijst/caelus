"""move description from plan to plan_template_version

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-22 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add description column to plan_template_version
    op.add_column(
        "plan_template_version",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # 2. Copy each plan's description to its canonical template version
    op.execute(sa.text(
        "UPDATE plan_template_version SET description = plan.description "
        "FROM plan "
        "WHERE plan.template_id = plan_template_version.id "
        "AND plan.description IS NOT NULL"
    ))

    # 3. Drop description column from plan
    op.drop_column("plan", "description")


def downgrade() -> None:
    # 1. Add description column back to plan
    op.add_column(
        "plan",
        sa.Column("description", sa.Text(), nullable=True),
    )

    # 2. Copy description from canonical template back to plan
    op.execute(sa.text(
        "UPDATE plan SET description = plan_template_version.description "
        "FROM plan_template_version "
        "WHERE plan.template_id = plan_template_version.id "
        "AND plan_template_version.description IS NOT NULL"
    ))

    # 3. Drop description column from plan_template_version
    op.drop_column("plan_template_version", "description")
