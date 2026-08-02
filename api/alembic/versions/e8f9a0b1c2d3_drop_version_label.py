"""drop dead version_label from product_template_version

`version_label` was a speculative, spec-inherited field that no code path ever
read. It is NULL for every row in dev and prod (109/109), and the admin page
redesign explicitly declined it in favor of the template's DB id. Dropping the
column is therefore data-lossless and needs no backfill.

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-08-02 00:00:00.000000

"""
import sqlmodel

from alembic import op
import sqlalchemy as sa


revision = 'e8f9a0b1c2d3'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.drop_column('version_label')


def downgrade() -> None:
    # Re-added as nullable, matching the original definition in 10fb17efd947.
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.add_column(
            sa.Column('version_label', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
