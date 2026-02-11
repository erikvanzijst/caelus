"""add unique constraints for product name with deleted flag and deployment uniqueness"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_unique_constraints_20240210"
down_revision = "7b6bcc66b915"
branch_labels = None
depends_on = None


def upgrade():
    # Drop the existing unique index on product name
    op.drop_index("ix_product_name", table_name="product")
    # Use batch mode for SQLite to add unique constraints
    with op.batch_alter_table("product") as batch_op:
        batch_op.create_unique_constraint("uq_product_name_deleted", ["name", "deleted"])
    with op.batch_alter_table("deployment") as batch_op:
        batch_op.create_unique_constraint(
            "uq_deployment_user_domain_template_deleted",
            ["user_id", "domainname", "template_id", "deleted"],
        )


def downgrade():
    # Drop the compound unique constraints using batch mode for SQLite
    with op.batch_alter_table("deployment") as batch_op:
        batch_op.drop_constraint("uq_deployment_user_domain_template_deleted", type_="unique")
    with op.batch_alter_table("product") as batch_op:
        batch_op.drop_constraint("uq_product_name_deleted", type_="unique")
    # Recreate the original unique index on product name
    op.create_index("ix_product_name", "product", ["name"], unique=True)
