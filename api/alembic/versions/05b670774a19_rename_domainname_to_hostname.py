"""rename domainname to hostname

Revision ID: 05b670774a19
Revises: 0db0c317d954
Create Date: 2026-03-13 11:39:04.302246

"""
from alembic import op
import sqlalchemy as sa


revision = '05b670774a19'
down_revision = '0db0c317d954'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename column
    op.alter_column("deployment", "domainname", new_column_name="hostname")

    # Drop old indexes that reference 'domainname'
    op.drop_index("ix_deployment_domainname", table_name="deployment")
    op.drop_index("uq_domainname_active", table_name="deployment")
    op.drop_index("uq_deployment_active", table_name="deployment")

    # Recreate indexes referencing 'hostname'
    op.create_index("ix_deployment_hostname", "deployment", ["hostname"], unique=False)
    op.create_index(
        "uq_hostname_active",
        "deployment",
        ["hostname"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", "hostname", "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )


def downgrade() -> None:
    # Drop new indexes
    op.drop_index("uq_deployment_active", table_name="deployment")
    op.drop_index("uq_hostname_active", table_name="deployment")
    op.drop_index("ix_deployment_hostname", table_name="deployment")

    # Rename column back
    op.alter_column("deployment", "hostname", new_column_name="domainname")

    # Recreate original indexes referencing 'domainname'
    op.create_index("ix_deployment_domainname", "deployment", ["domainname"], unique=False)
    op.create_index(
        "uq_domainname_active",
        "deployment",
        ["domainname"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", "domainname", "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
