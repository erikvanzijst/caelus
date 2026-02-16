from __future__ import annotations

import json
from pathlib import Path

import typer

from app.db import session_scope
from app.models import (
    UserCreate,
    DeploymentCreate,
    ProductTemplateVersionCreate,
    ProductCreate,
    ProductUpdate,
)
from app.services import templates as template_service, deployments as deployment_service, \
    products as product_service, users as user_service
from app.services.errors import NotFoundError

app = typer.Typer(help="Caelus CLI", pretty_exceptions_show_locals=False)


def _parse_user_values(
    *,
    user_values_json: str | None,
    user_values_file: Path | None,
) -> dict | None:
    if user_values_json is not None and user_values_file is not None:
        raise ValueError("Provide only one of --user-values-json or --user-values-file")

    if user_values_json is not None:
        try:
            parsed = json.loads(user_values_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON for --user-values-json: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("--user-values-json must decode to a JSON object")
        return parsed

    if user_values_file is not None:
        try:
            content = user_values_file.read_text()
        except OSError as exc:
            raise ValueError(f"Unable to read --user-values-file: {exc}") from exc
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in --user-values-file: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("--user-values-file must contain a JSON object")
        return parsed

    return None


@app.command("create-user")
def create_user(email: str) -> None:
    with session_scope() as session:
        user = user_service.create_user(session, UserCreate(email=email))
        typer.echo(f"Created user: {user}")


@app.command("delete-user")
def delete_user(user_id: int) -> None:
    with session_scope() as session:
        user = user_service.delete_user(session, user_id=user_id)
        typer.echo(f"Deleted user: {user}")


@app.command("list-users")
def list_users() -> None:
    with session_scope() as session:
        for user in user_service.list_users(session):
            typer.echo(user)


@app.command("get-user")
def get_user(user_id: int) -> None:
    with session_scope() as session:
        try:
            user = user_service.get_user(session, user_id=user_id)
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(user)


@app.command("create-product")
def create_product(name: str, description: str, template_id: int | None = None) -> None:
    with session_scope() as session:
        product = product_service.create_product(
            session,
            payload=ProductCreate(name=name, description=description, template_id=template_id),
        )
        typer.echo(f"Created product {product}")


@app.command("update-product")
def update_product(
    product_id: int,
    *,
    template_id: int | None = typer.Option(None, "--template-id"),
    description: str | None = typer.Option(None, "--description"),
) -> None:
    """Update a product's template_id and/or description."""
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
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(
            f"Updated product {product.id} template_id={product.template_id} description={product.description}"
        )


@app.command("delete-product")
def delete_product(product_id: int) -> None:
    with session_scope() as session:
        product = product_service.delete_product(session, product_id=product_id)
        typer.echo(f"Deleted product {product.id}")


@app.command("list-products")
def list_products() -> None:
    with session_scope() as session:
        for product in product_service.list_products(session):
            typer.echo(f"{product.id} {product.name}")


@app.command("get-product")
def get_product(product_id: int) -> None:
    with session_scope() as session:
        try:
            product = product_service.get_product(session, product_id=product_id)
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(product)


@app.command("create-template")
def create_template(product_id: int, chart_ref: str, chart_version: str) -> None:
    with session_scope() as session:
        try:
            template = template_service.create_template(
                session,
                ProductTemplateVersionCreate(product_id=product_id, chart_ref=chart_ref, chart_version=chart_version)
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Created template {template.id} for product {product_id}")


@app.command("list-templates")
def list_templates(product_id: int) -> None:
    with session_scope() as session:
        for template in template_service.list_templates(session, product_id=product_id):
            typer.echo(template)


@app.command("get-template")
def get_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
        try:
            template = template_service.get_template(
                session,
                product_id=product_id,
                template_id=template_id,
            )
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(template)


@app.command("delete-template")
def delete_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
        template = template_service.delete_template(
            session, product_id=product_id, template_id=template_id
        )
        typer.echo(f"Deleted template {template.id}")


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
        parsed_user_values = _parse_user_values(
            user_values_json=user_values_json,
            user_values_file=user_values_file,
        )
    except ValueError as e:
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
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Created deployment: {deployment}")


@app.command("list-deployments")
def list_deployments(user_id: int) -> None:
    with session_scope() as session:
        for deployment in deployment_service.list_deployments(session, user_id=user_id):
            typer.echo(deployment)


@app.command("get-deployment")
def get_deployment(user_id: int, deployment_id: int) -> None:
    with session_scope() as session:
        try:
            deployment = deployment_service.get_deployment(
                session,
                user_id=user_id,
                deployment_id=deployment_id,
            )
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(deployment)


@app.command("delete-deployment")
def delete_deployment(user_id: int, deployment_id: int) -> None:
    with session_scope() as session:
        try:
            deployment = deployment_service.delete_deployment(
                session, user_id=user_id, deployment_id=deployment_id
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Deleted deployment {deployment.id}")


if __name__ == "__main__":
    app()
