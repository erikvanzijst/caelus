"""add mollie payment integration schema

Add Mollie-related columns to user and subscription tables,
drop external_ref from subscription, extend payment_status enum,
and create mollie_payment table.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Extend payment_status enum with 'pending' (PostgreSQL only;
    #    SQLite stores enums as plain strings so no action needed)
    # ------------------------------------------------------------------
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE paymentstatus ADD VALUE IF NOT EXISTS 'pending'"))

    # ------------------------------------------------------------------
    # 2. Add mollie_customer_id to user table
    # ------------------------------------------------------------------
    op.add_column("user", sa.Column("mollie_customer_id", sa.String(), nullable=True))

    # ------------------------------------------------------------------
    # 3. Modify subscription: add Mollie fields, drop external_ref
    # ------------------------------------------------------------------
    op.add_column("subscription", sa.Column("mollie_subscription_id", sa.String(), nullable=True))
    op.add_column("subscription", sa.Column("mollie_mandate_id", sa.String(), nullable=True))
    op.drop_column("subscription", "external_ref")

    # ------------------------------------------------------------------
    # 4. Create mollie_payment table
    # ------------------------------------------------------------------
    op.create_table(
        "mollie_payment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("mollie_payment_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open", "pending", "authorized", "paid",
                "canceled", "expired", "failed",
                name="molliepaymentstatus",
            ),
            nullable=False,
        ),
        sa.Column("sequence_type", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mollie_payment_id"),
    )
    op.create_index(
        "ix_mollie_payment_subscription_id",
        "mollie_payment",
        ["subscription_id"],
    )


def downgrade() -> None:
    # Drop mollie_payment table and its enum
    op.drop_index("ix_mollie_payment_subscription_id", table_name="mollie_payment")
    op.drop_table("mollie_payment")
    sa.Enum(name="molliepaymentstatus").drop(op.get_bind(), checkfirst=True)

    # Restore external_ref, drop Mollie columns from subscription
    op.add_column("subscription", sa.Column("external_ref", sa.String(), nullable=True))
    op.drop_column("subscription", "mollie_mandate_id")
    op.drop_column("subscription", "mollie_subscription_id")

    # Drop mollie_customer_id from user
    op.drop_column("user", "mollie_customer_id")

    # Note: PostgreSQL does not support removing enum values without
    # recreating the type. The 'pending' value in paymentstatus will
    # remain after downgrade.
