"""add pricing and billing tables

Create plan, plan_template_version, and subscription tables.
Backfill a free plan per product, a subscription per deployment,
and add subscription_id FK on deployment.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create plan table (template_id FK added later to break cycle)
    # ------------------------------------------------------------------
    op.create_table(
        "plan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_product_id", "plan", ["product_id"])
    op.create_index(
        "uq_plan_name_active",
        "plan",
        ["product_id", sa.text("lower(name)")],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------
    # 2. Create plan_template_version table
    # ------------------------------------------------------------------
    op.create_table(
        "plan_template_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column(
            "billing_interval",
            sa.Enum("monthly", "annual", name="billinginterval"),
            nullable=False,
        ),
        sa.Column("storage_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["plan.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plan_template_version_plan_id",
        "plan_template_version",
        ["plan_id"],
    )

    # Now add the deferred FK from plan.template_id -> plan_template_version.id
    op.create_foreign_key(
        "fk_plan_template_id",
        "plan",
        "plan_template_version",
        ["template_id"],
        ["id"],
    )
    op.create_index("ix_plan_template_id", "plan", ["template_id"])

    # ------------------------------------------------------------------
    # 3. Create subscription table
    # ------------------------------------------------------------------
    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_template_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "cancelled", name="subscriptionstatus"),
            nullable=False,
        ),
        sa.Column(
            "payment_status",
            sa.Enum("current", "arrears", name="paymentstatus"),
            nullable=False,
        ),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("external_ref", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_template_id"], ["plan_template_version.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscription_plan_template_id",
        "subscription",
        ["plan_template_id"],
    )
    op.create_index("ix_subscription_user_id", "subscription", ["user_id"])

    # ------------------------------------------------------------------
    # 4. Backfill: free plan + template per product
    # ------------------------------------------------------------------

    # Insert a free Plan for each existing product
    op.execute(sa.text(
        "INSERT INTO plan (name, description, product_id, created_at) "
        "SELECT 'Free', 'Everything for free', id, CURRENT_TIMESTAMP "
        "FROM product WHERE deleted_at IS NULL"
    ))

    # Insert a PlanTemplateVersion for each new plan
    op.execute(sa.text(
        "INSERT INTO plan_template_version "
        "(plan_id, price_cents, billing_interval, storage_bytes, created_at) "
        "SELECT id, 0, 'monthly', 0, CURRENT_TIMESTAMP FROM plan"
    ))

    # Set each plan's canonical template_id
    op.execute(sa.text(
        "UPDATE plan SET template_id = ("
        "  SELECT ptv.id FROM plan_template_version ptv "
        "  WHERE ptv.plan_id = plan.id "
        "  LIMIT 1"
        ")"
    ))

    # ------------------------------------------------------------------
    # 5. Backfill: subscription per deployment
    # ------------------------------------------------------------------
    # For each deployment, create a subscription linked to the free
    # template for the deployment's product (found via desired_template_id
    # -> product_template_version -> product -> plan -> plan_template_version).
    op.execute(sa.text(
        "INSERT INTO subscription "
        "(plan_template_id, user_id, status, payment_status, created_at) "
        "SELECT "
        "  ptv.id, "
        "  d.user_id, "
        "  'active', "
        "  'current', "
        "  d.created_at "
        "FROM deployment d "
        "JOIN product_template_version tv ON d.desired_template_id = tv.id "
        "JOIN plan p ON p.product_id = tv.product_id "
        "JOIN plan_template_version ptv ON ptv.plan_id = p.id "
        "WHERE p.deleted_at IS NULL"
    ))

    # ------------------------------------------------------------------
    # 6. Add subscription_id to deployment, backfill, make NOT NULL
    # ------------------------------------------------------------------
    op.add_column(
        "deployment",
        sa.Column("subscription_id", sa.Integer(), nullable=True),
    )

    # Backfill: match each deployment to its subscription via the same
    # product -> plan -> plan_template_version chain.
    op.execute(sa.text(
        "UPDATE deployment SET subscription_id = ("
        "  SELECT s.id FROM subscription s "
        "  JOIN plan_template_version ptv ON s.plan_template_id = ptv.id "
        "  JOIN plan p ON ptv.plan_id = p.id "
        "  JOIN product_template_version tv ON p.product_id = tv.product_id "
        "  WHERE tv.id = deployment.desired_template_id "
        "  AND s.user_id = deployment.user_id "
        "  LIMIT 1"
        ")"
    ))

    op.alter_column("deployment", "subscription_id", nullable=False)

    op.create_foreign_key(
        "fk_deployment_subscription_id",
        "deployment",
        "subscription",
        ["subscription_id"],
        ["id"],
    )
    op.create_index(
        "ix_deployment_subscription_id",
        "deployment",
        ["subscription_id"],
    )


def downgrade() -> None:
    # Drop subscription_id from deployment
    op.drop_index("ix_deployment_subscription_id", table_name="deployment")
    op.drop_constraint("fk_deployment_subscription_id", "deployment", type_="foreignkey")
    op.drop_column("deployment", "subscription_id")

    # Drop subscription table
    op.drop_index("ix_subscription_user_id", table_name="subscription")
    op.drop_index("ix_subscription_plan_template_id", table_name="subscription")
    op.drop_table("subscription")

    # Drop plan.template_id FK and index before dropping plan_template_version
    op.drop_index("ix_plan_template_id", table_name="plan")
    op.drop_constraint("fk_plan_template_id", "plan", type_="foreignkey")

    # Drop plan_template_version table
    op.drop_index("ix_plan_template_version_plan_id", table_name="plan_template_version")
    op.drop_table("plan_template_version")

    # Drop plan table
    op.drop_index("uq_plan_name_active", table_name="plan")
    op.drop_index("ix_plan_product_id", table_name="plan")
    op.drop_table("plan")

    # Drop enum types (PostgreSQL only, no-op on SQLite)
    sa.Enum(name="billinginterval").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="subscriptionstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="paymentstatus").drop(op.get_bind(), checkfirst=True)
