"""deployment v2 fields and user admin

Revision ID: 3c6f4e851d22
Revises: 0f2f16f17a91
Create Date: 2026-02-15 00:10:00.000000

"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "3c6f4e851d22"
down_revision = "0f2f16f17a91"
branch_labels = None
depends_on = None

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_DASH_RUN_RE = re.compile(r"-+")
_MAX_DNS_LABEL_LEN = 63
_SUFFIX_LEN = 6
_BASE_MAX_LEN = _MAX_DNS_LABEL_LEN - (_SUFFIX_LEN + 1)
_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def _slugify(value: str) -> str:
    lowered = value.lower()
    replaced = _NON_ALNUM_RE.sub("-", lowered)
    collapsed = _DASH_RUN_RE.sub("-", replaced)
    return collapsed.strip("-")


def _to_base36(num: int) -> str:
    if num <= 0:
        return "0"
    out: list[str] = []
    n = num
    while n:
        n, rem = divmod(n, 36)
        out.append(_BASE36[rem])
    return "".join(reversed(out))


def _suffix_for_id(row_id: int) -> str:
    return _to_base36(row_id).rjust(_SUFFIX_LEN, "0")[-_SUFFIX_LEN:]


def _build_uid(product_name: str | None, user_email: str | None, row_id: int) -> str:
    product_slug = _slugify(product_name or "")
    user_slug = _slugify(user_email or "")
    parts = [p for p in (product_slug, user_slug) if p]
    base = "-".join(parts) if parts else "dep"
    base = base[:_BASE_MAX_LEN].strip("-") or "dep"
    return f"{base}-{_suffix_for_id(row_id)}"


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")))

    with op.batch_alter_table("deployment") as batch_op:
        batch_op.add_column(sa.Column("deployment_uid", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("namespace_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("release_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
        batch_op.add_column(sa.Column("desired_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("applied_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("user_values_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="pending",
            )
        )
        batch_op.add_column(sa.Column("generation", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("last_reconcile_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_deployment_desired_template_id",
            "product_template_version",
            ["desired_template_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_deployment_applied_template_id",
            "product_template_version",
            ["applied_template_id"],
            ["id"],
        )

    conn = op.get_bind()
    op.execute(sa.text("UPDATE user SET is_admin = 0 WHERE is_admin IS NULL"))
    op.execute(sa.text("UPDATE deployment SET desired_template_id = template_id WHERE desired_template_id IS NULL"))
    op.execute(sa.text("UPDATE deployment SET status = 'pending' WHERE status IS NULL OR status = ''"))
    op.execute(sa.text("UPDATE deployment SET generation = 1 WHERE generation IS NULL"))

    rows = conn.execute(
        sa.text(
            """
            SELECT d.id AS deployment_id, d.deployment_uid, u.email, p.name AS product_name
            FROM deployment d
            LEFT JOIN "user" u ON u.id = d.user_id
            LEFT JOIN product_template_version t ON t.id = d.template_id
            LEFT JOIN product p ON p.id = t.product_id
            """
        )
    ).mappings()

    for row in rows:
        dep_id = int(row["deployment_id"])
        deployment_uid = row["deployment_uid"] or _build_uid(row["product_name"], row["email"], dep_id)
        conn.execute(
            sa.text(
                """
                UPDATE deployment
                SET deployment_uid = :uid,
                    namespace_name = COALESCE(namespace_name, :uid),
                    release_name = COALESCE(release_name, :uid)
                WHERE id = :dep_id
                """
            ),
            {"uid": deployment_uid, "dep_id": dep_id},
        )

    with op.batch_alter_table("deployment") as batch_op:
        batch_op.alter_column("deployment_uid", nullable=False)
        batch_op.alter_column("namespace_name", nullable=False)
        batch_op.alter_column("release_name", nullable=False)
        batch_op.alter_column("desired_template_id", nullable=False)

    op.create_index(op.f("ix_deployment_status"), "deployment", ["status"], unique=False)
    op.create_index(
        op.f("ix_deployment_desired_template_id"),
        "deployment",
        ["desired_template_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_applied_template_id"),
        "deployment",
        ["applied_template_id"],
        unique=False,
    )
    op.create_index(op.f("ix_deployment_deployment_uid"), "deployment", ["deployment_uid"], unique=False)
    op.create_index(op.f("ix_deployment_namespace_name"), "deployment", ["namespace_name"], unique=False)
    op.create_index(op.f("ix_deployment_release_name"), "deployment", ["release_name"], unique=False)
    op.create_index(
        "uq_deployment_uid_active",
        "deployment",
        ["deployment_uid"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_namespace_name_active",
        "deployment",
        ["namespace_name"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_namespace_name_active", table_name="deployment", sqlite_where=sa.text("deleted_at IS NULL"))
    op.drop_index("uq_deployment_uid_active", table_name="deployment", sqlite_where=sa.text("deleted_at IS NULL"))
    op.drop_index(op.f("ix_deployment_release_name"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_namespace_name"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_deployment_uid"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_applied_template_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_desired_template_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_status"), table_name="deployment")

    with op.batch_alter_table("deployment") as batch_op:
        batch_op.drop_constraint("fk_deployment_applied_template_id", type_="foreignkey")
        batch_op.drop_constraint("fk_deployment_desired_template_id", type_="foreignkey")
        batch_op.drop_column("last_reconcile_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("generation")
        batch_op.drop_column("status")
        batch_op.drop_column("user_values_json")
        batch_op.drop_column("applied_template_id")
        batch_op.drop_column("desired_template_id")
        batch_op.drop_column("release_name")
        batch_op.drop_column("namespace_name")
        batch_op.drop_column("deployment_uid")

    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_column("is_admin")

