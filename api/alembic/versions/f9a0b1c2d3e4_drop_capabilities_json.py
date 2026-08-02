"""drop dead capabilities_json from product_template_version

`capabilities_json` was a speculative, spec-inherited container for four
upgrade flags (supports_domain_change, supports_inplace_upgrade,
requires_admin_upgrade, requires_maintenance_mode). Only the empty container
was ever implemented; none of the flags were. It is NULL for every row in dev
and prod (109/109) and no code path ever read it. Dropping the column is
therefore data-lossless and needs no backfill.

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f9a0b1c2d3e4'
down_revision = 'e8f9a0b1c2d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.drop_column('capabilities_json')


def downgrade() -> None:
    # Re-added as nullable JSON, matching the original definition in
    # 10fb17efd947.
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.add_column(
            sa.Column('capabilities_json', sa.JSON(), nullable=True)
        )
