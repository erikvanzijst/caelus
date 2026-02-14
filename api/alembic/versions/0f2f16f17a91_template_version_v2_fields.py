"""template version v2 fields

Revision ID: 0f2f16f17a91
Revises: 7f754e435ae2
Create Date: 2026-02-14 23:55:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "0f2f16f17a91"
down_revision = "7f754e435ae2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("product_template_version") as batch_op:
        batch_op.add_column(sa.Column("version_label", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "package_type",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="helm-chart",
            )
        )
        batch_op.add_column(sa.Column("chart_ref", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("chart_version", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("chart_digest", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("default_values_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("values_schema_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("capabilities_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("health_timeout_sec", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE product_template_version "
            "SET package_type = 'helm-chart' "
            "WHERE package_type IS NULL OR package_type = ''"
        )
    )

    with op.batch_alter_table("product_template_version") as batch_op:
        batch_op.create_check_constraint(
            "ck_product_template_package_type",
            "package_type IN ('helm-chart')",
        )


def downgrade() -> None:
    with op.batch_alter_table("product_template_version") as batch_op:
        batch_op.drop_constraint("ck_product_template_package_type", type_="check")
        batch_op.drop_column("health_timeout_sec")
        batch_op.drop_column("capabilities_json")
        batch_op.drop_column("values_schema_json")
        batch_op.drop_column("default_values_json")
        batch_op.drop_column("chart_digest")
        batch_op.drop_column("chart_version")
        batch_op.drop_column("chart_ref")
        batch_op.drop_column("package_type")
        batch_op.drop_column("version_label")

