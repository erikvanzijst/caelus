"""lowercase existing hostnames

Revision ID: b4a8f1c2d3e5
Revises: a1b2c3d4e5f7
Create Date: 2026-03-29 00:00:00.000000

"""
from alembic import op


revision = 'b4a8f1c2d3e5'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE deployment SET hostname = LOWER(hostname) WHERE hostname != LOWER(hostname)")


def downgrade() -> None:
    # Cannot restore original casing — this is a one-way data normalization.
    pass
