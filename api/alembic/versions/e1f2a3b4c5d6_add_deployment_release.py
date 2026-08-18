"""add deployment_release ledger

Introduces the release: the record of one rollout of a deployment, created by
the request that asks for it and completed by the reconciler that applies it.

Three things make this migration less ordinary than an additive table:

  1. The reference between `deployment` and `deployment_release` is mutual, so
     neither table can carry its foreign key from the start. Both tables are
     created (or extended) first and the constraints are added last, DEFERRABLE
     INITIALLY DEFERRED so that a single transaction may insert the deployment
     -- carrying an id for a release that does not exist yet -- before the
     release itself.

  2. `deployment.desired_release_id` is NOT NULL, which is only possible
     because every pre-existing deployment is backfilled a release here.
     Without it, a deployment predating this migration would have nothing for
     the first reconcile it gets to apply -- a Mollie webhook unblocking a
     `pending` row, or a lease reclaim of a job enqueued before the deploy.

  3. `applied_release_id` is backfilled only where `applied_template_id IS NOT
     NULL`, which is the existing record that something was actually applied.
     Blanket-setting it would have a `pending` deployment claiming to run
     something it never ran.

Note that the backfill covers **every** deployment row, deleted ones included.
NOT NULL is table-wide and soft-deleted deployments are retained rows, so
excluding them is not available; the release they receive simply records what
they last desired.

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-08-18 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. The ledger table. No `status` column (status derives from the three
    #    outcome columns) and no `image` column (the image lives in
    #    `values_json` and is reachable through `build_id`).
    op.create_table(
        "deployment_release",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Uuid(), nullable=True),
        sa.Column("values_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("helm_revision", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["product_template_version.id"]),
        sa.ForeignKeyConstraint(["build_id"], ["build.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deployment_id", "number", name="uq_release_number"),
    )
    op.create_index(
        "ix_deployment_release_deployment_id", "deployment_release", ["deployment_id"]
    )
    op.create_index("ix_deployment_release_build_id", "deployment_release", ["build_id"])

    # 2. The pointers, nullable for now so the backfill has somewhere to land.
    op.add_column("deployment", sa.Column("desired_release_id", sa.Uuid(), nullable=True))
    op.add_column("deployment", sa.Column("applied_release_id", sa.Uuid(), nullable=True))

    # 3. Backfill one release per deployment, numbered 1, carrying what the
    #    deployment currently desires. `created_at` is the deployment's own, so
    #    the release does not claim to have been requested at migration time.
    op.execute(
        """
        INSERT INTO deployment_release
            (id, number, deployment_id, template_id, build_id, values_json, created_at)
        SELECT
            gen_random_uuid(), 1, d.id, d.desired_template_id, NULL,
            d.user_values_json, d.created_at
        FROM deployment d
        """
    )
    op.execute(
        """
        UPDATE deployment d
        SET desired_release_id = r.id
        FROM deployment_release r
        WHERE r.deployment_id = d.id
        """
    )

    # 4. Only now can the NOT NULL hold.
    op.alter_column("deployment", "desired_release_id", nullable=False)

    # 5. Applied, only where something demonstrably was applied.
    op.execute(
        """
        UPDATE deployment
        SET applied_release_id = desired_release_id
        WHERE applied_template_id IS NOT NULL
        """
    )

    # 6. The constraints last, and deferred -- see the header.
    op.create_foreign_key(
        "fk_deployment_desired_release_id",
        "deployment",
        "deployment_release",
        ["desired_release_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_deployment_applied_release_id",
        "deployment",
        "deployment_release",
        ["applied_release_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_index("ix_deployment_desired_release_id", "deployment", ["desired_release_id"])
    op.create_index("ix_deployment_applied_release_id", "deployment", ["applied_release_id"])


def downgrade() -> None:
    op.drop_index("ix_deployment_applied_release_id", table_name="deployment")
    op.drop_index("ix_deployment_desired_release_id", table_name="deployment")
    op.drop_constraint("fk_deployment_applied_release_id", "deployment", type_="foreignkey")
    op.drop_constraint("fk_deployment_desired_release_id", "deployment", type_="foreignkey")
    op.drop_column("deployment", "applied_release_id")
    op.drop_column("deployment", "desired_release_id")
    op.drop_index("ix_deployment_release_build_id", table_name="deployment_release")
    op.drop_index("ix_deployment_release_deployment_id", table_name="deployment_release")
    op.drop_table("deployment_release")
