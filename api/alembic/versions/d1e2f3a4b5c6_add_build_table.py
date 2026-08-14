"""add build table

Creates the `build` table backing the build subsystem. Purely additive: no
existing table, column, or index is touched, so there is no data migration and
no compatibility window.

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-08-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "build",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("image", sa.String(), nullable=True),
        sa.Column("log", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_build_user_id", "build", ["user_id"])
    # Every build worker pass filters on status.
    op.create_index("ix_build_status", "build", ["status"])
    # At most one non-terminal build per artifact. Declared for both dialects
    # on purpose — tests run on SQLite and production on Postgres, and a
    # partial index declared for only one of them is a constraint that
    # silently does not exist in the other.
    op.create_index(
        "uq_open_build_per_artifact",
        "build",
        ["artifact_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_build_per_artifact", table_name="build")
    op.drop_index("ix_build_status", table_name="build")
    op.drop_index("ix_build_user_id", table_name="build")
    op.drop_table("build")
