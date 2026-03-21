from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import typer
import yaml
from fastapi.encoders import jsonable_encoder

from app.db import session_scope
from app.logging_config import configure_logging
from app.models import (
    UserCreate,
    DeploymentCreate,
    ProductTemplateVersionCreate,
    ProductCreate,
    ProductUpdate,
    DeploymentUpdate,
    PlanCreate,
    PlanUpdate,
    PlanTemplateVersionCreate,
    BillingInterval,
)
from app.services import (
    templates as template_service,
    deployments as deployment_service,
    products as product_service,
    users as user_service,
    reconcile as reconcile_service,
    jobs as jobs_service,
    plans as plan_service,
    subscriptions as subscription_service,
)
from app.services.errors import CaelusException
from app.services.reconcile_constants import (
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
)

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import UserORM

configure_logging()
logger = logging.getLogger(__name__)
app = typer.Typer(help="Caelus CLI", pretty_exceptions_show_locals=False)

# ── CLI authentication ────────────────────────────────────────────────

_cli_user_email: str | None = None


@app.callback()
def _main(
    as_user: str | None = typer.Option(
        None,
        "--as-user",
        envvar="CAELUS_USER_EMAIL",
        help="Email of the acting user (overrides CAELUS_USER_EMAIL).",
    ),
) -> None:
    global _cli_user_email
    _cli_user_email = as_user


def _require_cli_user(session: Session) -> UserORM:
    """Resolve the CLI user email to a UserORM, auto-creating if needed.

    Exits with code 1 when no email is configured.
    """
    if not _cli_user_email:
        typer.echo(
            "Error: No user email configured. "
            "Set CAELUS_USER_EMAIL or pass --as-user.",
            err=True,
        )
        raise typer.Exit(code=1)

    email = _cli_user_email.strip().lower()

    user = session.exec(
        select(UserORM).where(
            func.lower(UserORM.email) == email,
            UserORM.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    ).one_or_none()

    if user is None:
        user = UserORM(email=email)
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


def _parse_json_object_input(
    *,
    json_text: str | None,
    json_file: Path | None,
    json_option_name: str,
    file_option_name: str,
) -> dict:
    if json_text is not None and json_file is not None:
        raise ValueError(f"Provide only one of {json_option_name} or {file_option_name}")

    if json_text is not None:
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for {json_option_name}: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{json_option_name} must decode to a JSON object")
        return parsed

    if json_file is not None:
        try:
            content = json_file.read_text()
        except OSError as exc:
            raise ValueError(f"Unable to read {file_option_name}: {exc}") from exc
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {file_option_name}: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{file_option_name} must contain a JSON object")
        return parsed

    return {}


def _exit_for_domain_error(exc: CaelusException) -> None:
    logger.warning("CLI command failed with domain error: %s", exc)
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1)


def _echo_yaml_entity(entity: object) -> None:
    encoded = jsonable_encoder(entity)
    typer.echo(yaml.safe_dump(encoded, sort_keys=False), nl=False)


def _echo_yaml_stream_item(entity: object) -> None:
    encoded = jsonable_encoder(entity)
    typer.echo(yaml.safe_dump(encoded, sort_keys=False).rstrip())


@app.command("create-user")
def create_user(email: str) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            user = user_service.create_user(session, UserCreate(email=email))
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("delete-user")
def delete_user(user_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            user = user_service.delete_user(session, user_id=user_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("list-users")
def list_users() -> None:
    with session_scope() as session:
        _require_cli_user(session)
        _echo_yaml_entity(user_service.list_users(session))


@app.command("get-user")
def get_user(user_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            user = user_service.get_user(session, user_id=user_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("create-product")
def create_product(
    name: str,
    description: str,
    template_id: int | None = None,
    icon: Path | None = typer.Option(None, "--icon", help="Path to product icon image"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            icon_data = None
            if icon is not None:
                icon_data = icon.read_bytes()
            product = product_service.create_product(
                session,
                payload=ProductCreate(name=name, description=description, template_id=template_id),
                icon_data=icon_data,
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("update-product")
def update_product(
    product_id: int,
    *,
    template_id: int | None = typer.Option(None, "--template-id"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            product = product_service.update_product(
                session,
                product=ProductUpdate(
                    id=product_id,
                    template_id=template_id,
                    description=description,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("delete-product")
def delete_product(product_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            product = product_service.delete_product(session, product_id=product_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("list-products")
def list_products() -> None:
    with session_scope() as session:
        _require_cli_user(session)
        _echo_yaml_entity(product_service.list_products(session))


@app.command("get-product")
def get_product(product_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            product = product_service.get_product(session, product_id=product_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("create-template")
def create_template(
    product_id: int = typer.Option(
        ..., "--product-id", help="Product ID to associate with the template."
    ),
    chart_ref: str = typer.Option(
        ..., "--chart-ref", help="Chart reference (e.g. 'oci://example/chart')."
    ),
    chart_version: str = typer.Option(..., "--chart-version", help="Chart version (e.g. '1.2.3')."),
    chart_digest: str | None = typer.Option(
        None, "--chart-digest", help="Optional immutable digest for the chart artifact."
    ),
    version_label: str | None = typer.Option(
        None, "--version-label", help="Optional human-readable version label."
    ),
    system_values_json: str | None = typer.Option(
        None,
        "--system-values-json",
        help="JSON object string for template system values.",
    ),
    system_values_file: Path | None = typer.Option(
        None,
        "--system-values-file",
        help="Path to JSON file containing template system values object.",
    ),
    values_schema_json: str | None = typer.Option(
        None,
        "--values-schema-json",
        help="JSON object string for template values schema.",
    ),
    values_schema_file: Path | None = typer.Option(
        None,
        "--values-schema-file",
        help="Path to JSON file containing template values schema object.",
    ),
    capabilities_json: str | None = typer.Option(
        None,
        "--capabilities-json",
        help="JSON object string for template capabilities.",
    ),
    capabilities_file: Path | None = typer.Option(
        None,
        "--capabilities-file",
        help="Path to JSON file containing template capabilities object.",
    ),
) -> None:
    try:
        parsed_system_values = _parse_json_object_input(
            json_text=system_values_json,
            json_file=system_values_file,
            json_option_name="--system-values-json",
            file_option_name="--system-values-file",
        )
        parsed_values_schema = _parse_json_object_input(
            json_text=values_schema_json,
            json_file=values_schema_file,
            json_option_name="--values-schema-json",
            file_option_name="--values-schema-file",
        )
        parsed_capabilities = _parse_json_object_input(
            json_text=capabilities_json,
            json_file=capabilities_file,
            json_option_name="--capabilities-json",
            file_option_name="--capabilities-file",
        )
    except ValueError as e:
        logger.warning("Invalid template JSON input: %s", e)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    with session_scope() as session:
        _require_cli_user(session)
        try:
            template = template_service.create_template(
                session,
                ProductTemplateVersionCreate(
                    product_id=product_id,
                    chart_ref=chart_ref,
                    chart_version=chart_version,
                    chart_digest=chart_digest,
                    version_label=version_label,
                    system_values_json=parsed_system_values,
                    values_schema_json=parsed_values_schema,
                    capabilities_json=parsed_capabilities,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(template)


@app.command("list-templates")
def list_templates(product_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        _echo_yaml_entity(template_service.list_templates(session, product_id=product_id))


@app.command("get-template")
def get_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            template = template_service.get_template(
                session,
                product_id=product_id,
                template_id=template_id,
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(template)


@app.command("delete-template")
def delete_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            template = template_service.delete_template(
                session, product_id=product_id, template_id=template_id
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(template)


@app.command("create-deployment")
def create_deployment(
    *,
    user_id: int = typer.Option(..., "--user-id"),
    desired_template_id: int = typer.Option(..., "--desired-template-id"),
    plan_template_id: int | None = typer.Option(None, "--plan-template-id"),
    user_values_json: str | None = typer.Option(
        None,
        "--user-values-json",
        help='JSON object string for deployment user values, e.g. \'{"key":"value"}\'.',
    ),
    user_values_file: Path | None = typer.Option(
        None,
        "--user-values-file",
        help="Path to a JSON file containing a JSON object for deployment user values.",
    ),
) -> None:
    try:
        parsed_user_values = _parse_json_object_input(
            json_text=user_values_json,
            json_file=user_values_file,
            json_option_name="--user-values-json",
            file_option_name="--user-values-file",
        )
    except ValueError as e:
        logger.warning("Invalid deployment user values JSON input: %s", e)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    with session_scope() as session:
        _require_cli_user(session)
        try:
            deployment = deployment_service.create_deployment(
                session,
                payload=DeploymentCreate(
                    user_id=user_id,
                    desired_template_id=desired_template_id,
                    plan_template_id=plan_template_id,
                    user_values_json=parsed_user_values,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(deployment)


@app.command("list-deployments")
def list_deployments(
    user_id: int | None = typer.Argument(None, help="Filter deployments by user ID"),
    all_users: bool = typer.Option(False, "--all", help="List deployments for all users (admin only)"),
) -> None:
    with session_scope() as session:
        user = _require_cli_user(session)
        if all_users:
            if not user.is_admin:
                typer.echo("Error: --all requires admin privileges", err=True)
                raise typer.Exit(code=1)
            _echo_yaml_entity(deployment_service.list_deployments(session))
        else:
            _echo_yaml_entity(deployment_service.list_deployments(session, user_id=user_id))


@app.command("get-deployment")
def get_deployment(user_id: int, deployment_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            deployment = deployment_service.get_deployment(
                session,
                user_id=user_id,
                deployment_id=deployment_id,
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(deployment)


@app.command("delete-deployment")
def delete_deployment(user_id: int, deployment_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            deployment = deployment_service.delete_deployment(
                session, user_id=user_id, deployment_id=deployment_id
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(deployment)


@app.command("update-deployment")
def update_deployment(
    *,
    user_id: int = typer.Option(..., "--user-id"),
    deployment_id: int = typer.Option(..., "--deployment-id"),
    desired_template_id: int = typer.Option(..., "--desired-template-id"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            deployment = deployment_service.update_deployment(
                session,
                update=DeploymentUpdate(
                    user_id=user_id, id=deployment_id, desired_template_id=desired_template_id
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(deployment)


@app.command("reconcile")
def reconcile(
    deployment_id: int,
) -> None:
    with session_scope() as session:
        try:
            result = reconcile_service.DeploymentReconciler(session=session).reconcile(
                deployment_id
            )
        except CaelusException as e:
            _exit_for_domain_error(e)

        if result.status == "error":
            typer.echo(
                f"Error: Reconcile failed for deployment {deployment_id}: {result.last_error}",
                err=True,
            )
            raise typer.Exit(code=1)

        _echo_yaml_entity(result)


@app.command("worker")
def worker(
    concurrency: int = typer.Option(1, "--concurrency", "-c", help="Number of parallel job workers"),
    poll_seconds: float = typer.Option(1.0, "--poll-seconds", help="Sleep interval when no jobs are available"),
) -> None:
    if concurrency < 1:
        typer.echo("Error: --concurrency must be >= 1", err=True)
        raise typer.Exit(code=1)

    from app.worker import run_worker

    base_worker_id = os.environ.get("CAELUS_WORKER_ID") or f"worker-{int(time.time())}"
    run_worker(
        base_worker_id=base_worker_id,
        concurrency=concurrency,
        poll_seconds=poll_seconds,
        emit=_echo_yaml_stream_item,
    )


@app.command("jobs")
def jobs(
    failed: bool = typer.Option(False, "--failed", help="Show only failed jobs"),
    done: bool = typer.Option(False, "--done", help="Show only done jobs"),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Reverse run_after sort order"),
    deployment_id: int | None = typer.Option(
        None, "--deployment-id", "-d", help="Filter by deployment id"
    ),
) -> None:
    if failed and done:
        statuses = [JOB_STATUS_FAILED, JOB_STATUS_DONE]
    elif failed:
        statuses = [JOB_STATUS_FAILED]
    elif done:
        statuses = [JOB_STATUS_DONE]
    else:
        statuses = [JOB_STATUS_QUEUED, JOB_STATUS_RUNNING]

    with session_scope() as session:
        jobs_service_obj = jobs_service.JobService(session)
        jobs_list = jobs_service_obj.list_jobs(
            statuses=statuses, deployment_id=deployment_id, limit=1000
        )
        if reverse:
            jobs_list = list(reversed(jobs_list))
        _echo_yaml_entity(jobs_list)


# ── Plan commands ─────────────────────────────────────────────────────


@app.command("list-plans")
def list_plans(product_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            plans = plan_service.list_plans_for_product(session, product_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(plans)


@app.command("get-plan")
def get_plan(plan_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            plan = plan_service.get_plan(session, plan_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(plan)


@app.command("create-plan")
def create_plan(
    product_id: int = typer.Option(..., "--product-id"),
    name: str = typer.Option(..., "--name"),
    description: str | None = typer.Option(None, "--description"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            plan = plan_service.create_plan(
                session,
                product_id=product_id,
                payload=PlanCreate(name=name, description=description, sort_order=sort_order),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(plan)


@app.command("update-plan")
def update_plan(
    plan_id: int,
    name: str | None = typer.Option(None, "--name"),
    description: str | None = typer.Option(None, "--description"),
    template_id: int | None = typer.Option(None, "--template-id"),
    sort_order: int | None = typer.Option(None, "--sort-order"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            plan = plan_service.update_plan(
                session,
                plan_id=plan_id,
                payload=PlanUpdate(
                    name=name, description=description,
                    template_id=template_id, sort_order=sort_order,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(plan)


@app.command("delete-plan")
def delete_plan(plan_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            plan_service.delete_plan(session, plan_id=plan_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        typer.echo("Deleted")


@app.command("create-plan-template")
def create_plan_template(
    plan_id: int = typer.Option(..., "--plan-id"),
    price_cents: int = typer.Option(..., "--price-cents"),
    billing_interval: BillingInterval = typer.Option(..., "--billing-interval"),
    storage_bytes: int | None = typer.Option(None, "--storage-bytes"),
) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            tmpl = plan_service.create_plan_template_version(
                session,
                plan_id=plan_id,
                payload=PlanTemplateVersionCreate(
                    price_cents=price_cents,
                    billing_interval=billing_interval,
                    storage_bytes=storage_bytes,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(tmpl)


# ── Subscription commands ─────────────────────────────────────────────


@app.command("list-subscriptions")
def list_subscriptions(user_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        subs = subscription_service.list_subscriptions_for_user(session, user_id)
        _echo_yaml_entity(subs)


@app.command("cancel-subscription")
def cancel_subscription(subscription_id: int) -> None:
    with session_scope() as session:
        _require_cli_user(session)
        try:
            sub = subscription_service.cancel_subscription(
                session, subscription_id=subscription_id
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(sub)


if __name__ == "__main__":
    app()
