"""Add marketing metadata to product

Revision ID: c7d8e9f0a1b2
Revises: b4a8f1c2d3e5
Create Date: 2026-06-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b4a8f1c2d3e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product", sa.Column("category", sa.String(), nullable=True))
    op.add_column("product", sa.Column("replaces", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "replaces")
    op.drop_column("product", "category")
