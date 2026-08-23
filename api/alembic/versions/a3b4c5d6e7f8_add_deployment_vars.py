"""add deployment_var and release_var

Runtime configuration for a deployment's pod: an append-only history of
values, and the snapshot each release was created with.

Purely additive -- no existing table is touched and no data moves. Nothing
migrates off `deployment.user_values_json`, which keeps its current job of
configuring the chart. Rolling back is dropping the two tables; nothing else
references them.

Two column choices are load-bearing rather than stylistic:

  1. `deployment_var.id` is IDENTITY, not a plain sequence anyone may write:
     head resolution and the release snapshot both order by it, so it is the
     record of what was written after what.

  2. `value_encrypted` is nullable *because* NULL is the tombstone -- the
     marker that a key was deleted at that point in history. The check
     constraint ties it to `key_id`, so a row can neither name a key that
     encrypted nothing nor carry ciphertext without naming its key.

Revision ID: a3b4c5d6e7f8
Revises: e1f2a3b4c5d6
Create Date: 2026-08-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "a3b4c5d6e7f8"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_var",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=True),
        sa.Column("key_id", sa.String(length=8), nullable=True),
        sa.Column(
            "sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(value_encrypted IS NULL) = (key_id IS NULL)",
            name="ck_deployment_var_tombstone",
        ),
    )
    # Head resolution: the newest row per key within one deployment.
    op.create_index(
        "ix_deployment_var_head",
        "deployment_var",
        ["deployment_id", "key", sa.text("id DESC")],
    )
    # Key retirement and the re-encryption sweep.
    op.create_index("ix_deployment_var_key_id", "deployment_var", ["key_id"])

    op.create_table(
        "release_var",
        sa.Column("release_id", sa.Uuid(), nullable=False),
        sa.Column("var_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id"], ["deployment_release.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["var_id"], ["deployment_var.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("release_id", "var_id"),
    )
    op.create_index("ix_release_var_var", "release_var", ["var_id"])


def downgrade() -> None:
    op.drop_index("ix_release_var_var", table_name="release_var")
    op.drop_table("release_var")
    op.drop_index("ix_deployment_var_key_id", table_name="deployment_var")
    op.drop_index("ix_deployment_var_head", table_name="deployment_var")
    op.drop_table("deployment_var")
