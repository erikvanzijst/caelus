"""fix partial unique indexes

Revision ID: 5a86ca9171f3
Revises: 9b4e729fd792
Create Date: 2026-03-05 17:10:54.093011

"""
from alembic import op
import sqlalchemy as sa



revision = '5a86ca9171f3'
down_revision = '9b4e729fd792'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_deployment_active", table_name="deployment")
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", "domainname", "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("status != 'deleted'"),
        postgresql_where=sa.text("status <> 'deleted'"),
    )
    op.drop_index("uq_producttemplate_active", table_name="product_template_version")


def downgrade() -> None:
    op.create_index(
        "uq_producttemplate_active",
        "product_template_version",
        ["chart_ref", "chart_version", "product_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("uq_deployment_active", table_name="deployment")
    op.create_index(
        "uq_deployment_active",
        "deployment",
        ["user_id", "domainname", "desired_template_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
