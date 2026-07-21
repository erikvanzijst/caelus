"""record ToS acceptance on the user

Terms of Service acceptance is a user-level fact recorded once, not a
per-deployment one. This adds two nullable columns to `user`
(`tos_accepted_version`, `tos_accepted_at`) — NULL means "has not accepted yet",
so no backfill is needed — and drops the earlier per-deployment
`deployment.tos_version` column. There is no production data; the dev/test
database is reset to match.

Revision ID: d7e8f9a0b1c2
Revises: c7d8e9f0a1b2
Create Date: 2026-07-21 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd7e8f9a0b1c2'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Record acceptance on the user (nullable; NULL == not yet accepted).
    with op.batch_alter_table('user') as batch_op:
        batch_op.add_column(sa.Column('tos_accepted_version', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('tos_accepted_at', sa.DateTime(), nullable=True))

    # Drop the superseded per-deployment column (batch mode so SQLite rebuilds).
    with op.batch_alter_table('deployment') as batch_op:
        batch_op.drop_column('tos_version')


def downgrade() -> None:
    # Re-add the per-deployment column as nullable (no data to restore).
    with op.batch_alter_table('deployment') as batch_op:
        batch_op.add_column(sa.Column('tos_version', sa.String(), nullable=True))

    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('tos_accepted_at')
        batch_op.drop_column('tos_accepted_version')
