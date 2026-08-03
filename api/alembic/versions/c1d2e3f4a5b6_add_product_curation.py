"""Add catalog curation columns

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-08-03 00:00:00.000000

Adds the three columns that join a product row to its `products/catalog/`
file: `product.slug` (the stable catalog key, unique among non-deleted rows),
`product.curated` (whether the catalog owns the row), and
`product_template_version.catalog_commit` (the commit whose catalog produced a
template row).

Every existing product is backfilled to `curated = false` with a null slug, so
no product changes behavior until its catalog file is added and rolled out.

"""

from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("product", sa.Column("slug", sa.String(), nullable=True))
    op.add_column(
        "product",
        sa.Column("curated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Partial index so soft-deleted rows do not hold a slug hostage, matching
    # how the product name's uniqueness is scoped.
    op.create_index(
        "uq_product_slug_active",
        "product",
        ["slug"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column(
        "product_template_version", sa.Column("catalog_commit", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("product_template_version", "catalog_commit")
    op.drop_index("uq_product_slug_active", table_name="product")
    op.drop_column("product", "curated")
    op.drop_column("product", "slug")
