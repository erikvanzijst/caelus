"""record ToS acceptance on the user

Terms of Service acceptance is a user-level fact recorded once. This adds two
nullable columns to `user` (`tos_accepted_version`, `tos_accepted_at`) — NULL
means "has not accepted yet", so no backfill is needed. Acceptance is recorded
via POST /api/me/tos-acceptance; the deployment table carries no ToS field.

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


def downgrade() -> None:
    with op.batch_alter_table('user') as batch_op:
        batch_op.drop_column('tos_accepted_at')
        batch_op.drop_column('tos_accepted_version')
