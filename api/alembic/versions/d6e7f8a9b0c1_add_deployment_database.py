"""add deployment_database

One row per deployment that has a database on the tenant cluster. Its
absence is the "not provisioned" state, so nothing here backfills and no
column is added to `deployment` -- the platform's most-joined table gains
nothing for a subsystem most deployments never touch.

Purely additive. Rolling back drops the table; nothing references it.

Two column choices are load-bearing rather than stylistic:

  1. The foreign key does NOT cascade, unlike `deployment_var`'s. This row
     records objects that exist on a different server, and it must outlive
     the deployment's own deletion: `purge_after` is recorded on it, and the
     purge tick reads it to know there is still a database to drop.

  2. There is no `deleted_at`. Soft-deleting the row would invent a third
     state between "provisioned" and "not provisioned", and the row is
     already the thing that survives deletion.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-25

"""
from alembic import op
import sqlalchemy as sa


revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_database",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=True),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("db_name", sa.String(length=63), nullable=False),
        sa.Column("role_name", sa.String(length=63), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=False),
        sa.Column("key_id", sa.String(length=8), nullable=False),
        sa.Column(
            "quota_state",
            sa.String(length=16),
            server_default=sa.text("'ok'"),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("measured_at", sa.DateTime(), nullable=True),
        sa.Column("warned_threshold", sa.SmallInteger(), nullable=True),
        sa.Column("warned_at", sa.DateTime(), nullable=True),
        sa.Column("readonly_at", sa.DateTime(), nullable=True),
        sa.Column("blocked_at", sa.DateTime(), nullable=True),
        sa.Column("purge_after", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployment.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deployment_id"),
    )
    op.create_index(
        "ix_deployment_database_quota_state",
        "deployment_database",
        ["quota_state"],
    )
    # Partial: a deployment that was never deleted has no purge deadline and
    # does not belong in the index the purge tick scans.
    op.create_index(
        "ix_deployment_database_purge_after",
        "deployment_database",
        ["purge_after"],
        postgresql_where=sa.text("purge_after IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_deployment_database_purge_after", table_name="deployment_database")
    op.drop_index("ix_deployment_database_quota_state", table_name="deployment_database")
    op.drop_table("deployment_database")
