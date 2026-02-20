from __future__ import annotations

import json
import logging
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
    ProductUpdate, DeploymentUpdate,
)
from app.services import (templates as template_service, deployments as deployment_service,
                          products as product_service, users as user_service, reconcile as reconcile_service)
from app.services.errors import CaelusException

configure_logging()
logger = logging.getLogger(__name__)
app = typer.Typer(help="Caelus CLI", pretty_exceptions_show_locals=False)


def _parse_json_object_input(
    *,
    json_text: str | None,
    json_file: Path | None,
    json_option_name: str,
    file_option_name: str,
) -> dict | None:
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

    return None


def _exit_for_domain_error(exc: CaelusException) -> None:
    logger.warning("CLI command failed with domain error: %s", exc)
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1)


def _echo_yaml_entity(entity: object) -> None:
    encoded = jsonable_encoder(entity)
    typer.echo(yaml.safe_dump(encoded, sort_keys=False), nl=False)


@app.command("create-user")
def create_user(email: str) -> None:
    with session_scope() as session:
        try:
            user = user_service.create_user(session, UserCreate(email=email))
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("delete-user")
def delete_user(user_id: int) -> None:
    with session_scope() as session:
        try:
            user = user_service.delete_user(session, user_id=user_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("list-users")
def list_users() -> None:
    with session_scope() as session:
        _echo_yaml_entity(user_service.list_users(session))


@app.command("get-user")
def get_user(user_id: int) -> None:
    with session_scope() as session:
        try:
            user = user_service.get_user(session, user_id=user_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(user)


@app.command("create-product")
def create_product(name: str, description: str, template_id: int | None = None) -> None:
    with session_scope() as session:
        try:
            product = product_service.create_product(
                session,
                payload=ProductCreate(name=name, description=description, template_id=template_id),
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
        try:
            product = product_service.delete_product(session, product_id=product_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("list-products")
def list_products() -> None:
    with session_scope() as session:
        _echo_yaml_entity(product_service.list_products(session))


@app.command("get-product")
def get_product(product_id: int) -> None:
    with session_scope() as session:
        try:
            product = product_service.get_product(session, product_id=product_id)
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(product)


@app.command("create-template")
def create_template(
    product_id: int = typer.Option(..., "--product-id", help="Product ID to associate with the template."),
    chart_ref: str = typer.Option(..., "--chart-ref", help="Chart reference (e.g. 'oci://example/chart')."),
    chart_version: str = typer.Option(..., "--chart-version", help="Chart version (e.g. '1.2.3')."),
    chart_digest: str | None = typer.Option(
        None, "--chart-digest", help="Optional immutable digest for the chart artifact."
    ),
    version_label: str | None = typer.Option(
        None, "--version-label", help="Optional human-readable version label."
    ),
    default_values_json: str | None = typer.Option(
        None,
        "--default-values-json",
        help="JSON object string for template default values.",
    ),
    default_values_file: Path | None = typer.Option(
        None,
        "--default-values-file",
        help="Path to JSON file containing template default values object.",
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
        parsed_default_values = _parse_json_object_input(
            json_text=default_values_json,
            json_file=default_values_file,
            json_option_name="--default-values-json",
            file_option_name="--default-values-file",
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
        try:
            template = template_service.create_template(
                session,
                ProductTemplateVersionCreate(
                    product_id=product_id,
                    chart_ref=chart_ref,
                    chart_version=chart_version,
                    chart_digest=chart_digest,
                    version_label=version_label,
                    default_values_json=parsed_default_values,
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
        _echo_yaml_entity(template_service.list_templates(session, product_id=product_id))


@app.command("get-template")
def get_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
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
    domainname: str = typer.Option(..., "--domainname"),
    user_values_json: str | None = typer.Option(
        None,
        "--user-values-json",
        help="JSON object string for deployment user values, e.g. '{\"key\":\"value\"}'.",
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
        try:
            deployment = deployment_service.create_deployment(
                session,
                payload=DeploymentCreate(
                    user_id=user_id,
                    desired_template_id=desired_template_id,
                    domainname=domainname,
                    user_values_json=parsed_user_values,
                ),
            )
        except CaelusException as e:
            _exit_for_domain_error(e)
        _echo_yaml_entity(deployment)


@app.command("list-deployments")
def list_deployments(user_id: int) -> None:
    with session_scope() as session:
        _echo_yaml_entity(deployment_service.list_deployments(session, user_id=user_id))


@app.command("get-deployment")
def get_deployment(user_id: int, deployment_id: int) -> None:
    with session_scope() as session:
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
        try:
            deployment = deployment_service.update_deployment(
                session,
                update=DeploymentUpdate(user_id=user_id, id=deployment_id, desired_template_id=desired_template_id)
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
            result = reconcile_service.DeploymentReconciler(session=session).reconcile(deployment_id)
        except CaelusException as e:
            _exit_for_domain_error(e)

        if result.status == "error":
            typer.echo(
                f"Error: Reconcile failed for deployment {deployment_id}: {result.last_error}",
                err=True,
            )
            raise typer.Exit(code=1)

        _echo_yaml_entity(result)


if __name__ == "__main__":
    app()
