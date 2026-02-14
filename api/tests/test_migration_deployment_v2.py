from __future__ import annotations

import os
import subprocess
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


API_DIR = Path(__file__).resolve().parents[1]
BASELINE = "0f2f16f17a91"
REVISION = "3c6f4e851d22"


def _run_alembic(db_url: str, command: list[str]) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    subprocess.run(
        ["uv", "run", "--no-sync", "alembic", *command],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_upgrade_adds_deployment_v2_columns_and_backfills(tmp_path: Path) -> None:
    db_path = tmp_path / "deployment_v2_upgrade.db"
    db_url = f"sqlite:///{db_path}"

    _run_alembic(db_url, ["upgrade", BASELINE])

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO user (email, created_at, deleted_at)
                VALUES ('owner@example.com', CURRENT_TIMESTAMP, NULL)
                """
            )
        )
        user_id = conn.execute(text("SELECT id FROM user WHERE email = 'owner@example.com'")).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO product (name, description, created_at, deleted_at)
                VALUES ('hello-static', 'demo', CURRENT_TIMESTAMP, NULL)
                """
            )
        )
        product_id = conn.execute(text("SELECT id FROM product WHERE name = 'hello-static'")).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO product_template_version
                (product_id, docker_image_url, package_type, created_at, deleted_at)
                VALUES (:pid, 'legacy:latest', 'helm-chart', CURRENT_TIMESTAMP, NULL)
                """
            ),
            {"pid": product_id},
        )
        template_id = conn.execute(text("SELECT id FROM product_template_version WHERE product_id=:pid"), {"pid": product_id}).scalar_one()

        conn.execute(
            text(
                """
                INSERT INTO deployment
                (user_id, template_id, domainname, created_at, deleted_at)
                VALUES (:uid, :tid, 'cloud.example.com', CURRENT_TIMESTAMP, NULL)
                """
            ),
            {"uid": user_id, "tid": template_id},
        )

    _run_alembic(db_url, ["upgrade", REVISION])

    insp = inspect(engine)
    dep_cols = {c["name"] for c in insp.get_columns("deployment")}
    assert {
        "deployment_uid",
        "namespace_name",
        "release_name",
        "desired_template_id",
        "applied_template_id",
        "user_values_json",
        "status",
        "generation",
        "last_error",
        "last_reconcile_at",
    }.issubset(dep_cols)
    user_cols = {c["name"] for c in insp.get_columns("user")}
    assert "is_admin" in user_cols

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT deployment_uid, namespace_name, release_name,
                       desired_template_id, template_id, status, generation
                FROM deployment
                """
            )
        ).mappings().one()

        assert row["deployment_uid"] is not None
        assert row["namespace_name"] == row["deployment_uid"]
        assert row["release_name"] == row["deployment_uid"]
        assert row["desired_template_id"] == row["template_id"]
        assert row["status"] == "pending"
        assert row["generation"] == 1
        assert len(row["deployment_uid"]) <= 63

        is_admin = conn.execute(text("SELECT is_admin FROM user WHERE email='owner@example.com'")).scalar_one()
        assert is_admin in (0, False)


def test_downgrade_removes_deployment_v2_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "deployment_v2_downgrade.db"
    db_url = f"sqlite:///{db_path}"

    _run_alembic(db_url, ["upgrade", REVISION])
    _run_alembic(db_url, ["downgrade", BASELINE])

    engine = create_engine(db_url)
    insp = inspect(engine)
    dep_cols = {c["name"] for c in insp.get_columns("deployment")}
    removed = {
        "deployment_uid",
        "namespace_name",
        "release_name",
        "desired_template_id",
        "applied_template_id",
        "user_values_json",
        "status",
        "generation",
        "last_error",
        "last_reconcile_at",
    }
    assert removed.isdisjoint(dep_cols)

    user_cols = {c["name"] for c in insp.get_columns("user")}
    assert "is_admin" not in user_cols

