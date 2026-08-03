"""Add visibility to product

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-08-03 00:00:00.000000

The column is added with a server default of 'admin' so that rows created
outside the ORM stay hidden, then every pre-existing product is backfilled to
'public' to preserve today's behavior, in which every product is offered to
end users.

"""

from alembic import op
import sqlalchemy as sa


revision = "b1c2d3e4f5a6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


visibility_enum = sa.Enum("public", "admin", name="productvisibility")


def upgrade() -> None:
    bind = op.get_bind()
    # op.add_column does not create the PostgreSQL enum type for us the way
    # create_table does, so create it explicitly (a no-op on SQLite).
    visibility_enum.create(bind, checkfirst=True)
    op.add_column(
        "product",
        sa.Column(
            "visibility",
            visibility_enum,
            nullable=False,
            server_default="admin",
        ),
    )
    op.execute("UPDATE product SET visibility = 'public'")


def downgrade() -> None:
    op.drop_column("product", "visibility")
    visibility_enum.drop(op.get_bind(), checkfirst=True)
