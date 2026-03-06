"""Add rel_icon_path to product

Revision ID: 0db0c317d954
Revises: 5a86ca9171f3
Create Date: 2026-03-06 10:58:54.496922

"""

from alembic import op
import sqlalchemy as sa


revision = "0db0c317d954"
down_revision = "5a86ca9171f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product", sa.Column("rel_icon_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("product", "rel_icon_path")
