"""`caelus` plan commands: the plan allowances a template version carries."""

from __future__ import annotations

from typing import Any

import yaml
from sqlmodel import select

from app.db import session_scope


def _parse_yaml_stdout(result) -> Any:
    return yaml.safe_load(getattr(result, "stdout", result.output))


def _make_cli_user_admin(runner, app) -> None:
    from app.models import UserORM

    runner.invoke(app, ["list-users"])
    with session_scope() as session:
        user = session.exec(
            select(UserORM).where(UserORM.email == "cli-test@example.com")
        ).one()
        user.is_admin = True
        session.add(user)
        session.commit()


def _product_and_plan(runner, app, name: str = "Basic") -> tuple[int, int]:
    product = _parse_yaml_stdout(
        runner.invoke(app, ["create-product", "planprod", "A product with plans"])
    )
    plan = _parse_yaml_stdout(
        runner.invoke(
            app, ["create-plan", "--product-id", str(product["id"]), "--name", name]
        )
    )
    return product["id"], plan["id"]


def test_create_plan_template_carries_both_allowances(cli_runner):
    runner, app = cli_runner
    _make_cli_user_admin(runner, app)
    product_id, plan_id = _product_and_plan(runner, app)

    result = runner.invoke(
        app,
        [
            "create-plan-template",
            "--plan-id",
            str(plan_id),
            "--price-cents",
            "300",
            "--billing-interval",
            "monthly",
            "--storage-bytes",
            "1073741824",
            "--database-bytes",
            "1073741824",
        ],
    )
    assert result.exit_code == 0
    tmpl = _parse_yaml_stdout(result)
    assert tmpl["storage_bytes"] == 1073741824
    assert tmpl["database_bytes"] == 1073741824

    # Make it the plan's canonical terms so the listing carries it.
    assert (
        runner.invoke(
            app, ["update-plan", str(plan_id), "--template-id", str(tmpl["id"])]
        ).exit_code
        == 0
    )
    plans = _parse_yaml_stdout(runner.invoke(app, ["list-plans", str(product_id)]))
    assert [p["template"]["database_bytes"] for p in plans] == [1073741824]


def test_database_bytes_defaults_to_no_allowance(cli_runner):
    """Omitting the option leaves the plan granting no relational storage."""
    runner, app = cli_runner
    _make_cli_user_admin(runner, app)
    _, plan_id = _product_and_plan(runner, app, name="Free")

    tmpl = _parse_yaml_stdout(
        runner.invoke(
            app,
            [
                "create-plan-template",
                "--plan-id",
                str(plan_id),
                "--price-cents",
                "0",
                "--billing-interval",
                "monthly",
            ],
        )
    )
    assert tmpl["database_bytes"] is None
