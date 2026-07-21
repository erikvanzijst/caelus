"""add tos_version to deployment

Records the Terms of Service version (effective date) the user accepted when
creating a deployment. Existing rows predate the consent gate; since there is no
production data yet, they are backfilled to the current ToS effective date
(2026-07-01) and the column is made NOT NULL.

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

# Effective date of the current Terms of Service at the time of this migration.
CURRENT_TOS_VERSION = '2026-07-01'


def upgrade() -> None:
    # 1. Add the column nullable so existing rows can be backfilled.
    op.add_column('deployment', sa.Column('tos_version', sa.String(), nullable=True))

    # 2. Backfill existing deployments as having accepted the current terms.
    op.execute(
        sa.text("UPDATE deployment SET tos_version = :v").bindparams(v=CURRENT_TOS_VERSION)
    )

    # 3. Enforce NOT NULL now that every row has a value. Batch mode so the
    #    NOT NULL change also applies on SQLite (table-rebuild), not just the
    #    Postgres prod target.
    with op.batch_alter_table('deployment') as batch_op:
        batch_op.alter_column('tos_version', existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.drop_column('deployment', 'tos_version')
