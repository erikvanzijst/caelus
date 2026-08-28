"""add user_ssh_key

An account's registered SSH public keys. Owned by a user and scoped to no
deployment; nothing reads the table yet, so creating it grants no access.

Uniqueness is on (user_id, fingerprint) rather than on the key blob: the
fingerprint is a digest of that blob, so the guarantee is the same, and a
btree over the blob would exceed its 2704-byte row ceiling at RSA-16384.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_ssh_key",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("key_type", sa.String(length=64), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("bits", sa.SmallInteger(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_ssh_key_user_id", "user_ssh_key", ["user_id"])
    op.create_index(
        "uq_user_ssh_key_fingerprint",
        "user_ssh_key",
        ["user_id", "fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_ssh_key_fingerprint", table_name="user_ssh_key")
    op.drop_index("ix_user_ssh_key_user_id", table_name="user_ssh_key")
    op.drop_table("user_ssh_key")
