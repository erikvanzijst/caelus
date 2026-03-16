"""rename default_values_json to system_values_json

Revision ID: a1b2c3d4e5f6
Revises: 05b670774a19
Create Date: 2026-03-16 14:00:00.000000

"""
from alembic import op


revision = 'a1b2c3d4e5f6'
down_revision = '05b670774a19'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "product_template_version",
        "default_values_json",
        new_column_name="system_values_json",
    )


def downgrade() -> None:
    op.alter_column(
        "product_template_version",
        "system_values_json",
        new_column_name="default_values_json",
    )
