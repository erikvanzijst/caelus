"""drop dead health_timeout_sec from product_template_version

`health_timeout_sec` was ORM-only: it existed on ProductTemplateVersionORM but
never on ProductTemplateVersionBase, ...Create or ...Read, so there was no REST
field, no CLI flag and no write path of any kind. It is NULL for every row in
dev and prod (115/115) and could not structurally be anything else. Both
readers in reconcile.py therefore constant-folded to 300 and have been replaced
with an explicit HELM_TIMEOUT_SEC constant. Dropping the column is data-lossless
and needs no backfill.

Revision ID: a7b8c9d0e1f2
Revises: f9a0b1c2d3e4
Create Date: 2026-08-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7b8c9d0e1f2'
down_revision = 'f9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.drop_column('health_timeout_sec')


def downgrade() -> None:
    # Re-added as nullable Integer, matching the original definition in
    # 10fb17efd947.
    with op.batch_alter_table('product_template_version') as batch_op:
        batch_op.add_column(
            sa.Column('health_timeout_sec', sa.Integer(), nullable=True)
        )
