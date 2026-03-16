"""split deployment_uid into name and namespace

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-16 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add namespace column (nullable temporarily)
    op.add_column('deployment', sa.Column('namespace', sa.String(), nullable=True))

    # 2. Seed namespace from existing deployment_uid for all rows
    op.execute("UPDATE deployment SET namespace = deployment_uid")

    # 3. Make namespace NOT NULL
    op.alter_column('deployment', 'namespace', nullable=False)

    # 4. Rename deployment_uid -> name
    op.alter_column('deployment', 'deployment_uid', new_column_name='name')

    # 5. Drop old index, create new indexes
    op.drop_index('ix_deployment_deployment_uid', table_name='deployment')
    op.create_index('ix_deployment_name', 'deployment', ['name'])
    op.create_index('ix_deployment_namespace', 'deployment', ['namespace'])

    # 6. Add partial unique index on (namespace, name) for active deployments
    op.create_index(
        'uq_deployment_ns_name_active',
        'deployment',
        ['namespace', 'name'],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
        sqlite_where=sa.text("status != 'deleted'"),
    )


def downgrade() -> None:
    op.drop_index('uq_deployment_ns_name_active', table_name='deployment')
    op.drop_index('ix_deployment_namespace', table_name='deployment')
    op.drop_index('ix_deployment_name', table_name='deployment')
    op.alter_column('deployment', 'name', new_column_name='deployment_uid')
    op.create_index('ix_deployment_deployment_uid', 'deployment', ['deployment_uid'])
    op.drop_column('deployment', 'namespace')
