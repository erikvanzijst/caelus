from __future__ import annotations

import typer

from app.db import session_scope
from app.models import UserCreate, DeploymentCreate, ProductTemplateVersionCreate, ProductCreate
from app.services import deployments as deployment_service
from app.services import products as product_service
from app.services import templates as template_service
from app.services import users as user_service
from app.services.errors import NotFoundError

app = typer.Typer(help="Caelus CLI", pretty_exceptions_show_locals=False)


@app.command("create-user")
def create_user(email: str) -> None:
    with session_scope() as session:
        user = user_service.create_user(session, UserCreate(email=email))
        typer.echo(f"Created user: {user}")
        typer.echo(user)


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


@app.command("create-product")
def create_product(name: str, description: str, template_id: int | None = None) -> None:
    with session_scope() as session:
        product = product_service.create_product(
            session,
            payload=ProductCreate(name=name, description=description, template_id=template_id),
        )
        typer.echo(f"Created product {product}")


@app.command("update-product")
def update_product(product_id: int, template_id: int) -> None:
    """Update a product's template_id."""
    with session_scope() as session:
        try:
            product = product_service.update_product_template(
                session, product_id=product_id, template_id=template_id
            )
        except NotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Updated product {product.id} template_id to {product.template_id}")


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


@app.command("create-template")
def create_template(product_id: int, docker_image_url: str = "") -> None:
    with session_scope() as session:
        try:
            template = template_service.create_template(
                session,
                ProductTemplateVersionCreate(
                    product_id=product_id, docker_image_url=docker_image_url or None
                ),
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Created template {template.id} for product {product_id}")


@app.command("list-templates")
def list_templates(product_id: int) -> None:
    with session_scope() as session:
        for template in template_service.list_templates(session, product_id=product_id):
            typer.echo(template)


@app.command("delete-template")
def delete_template(product_id: int, template_id: int) -> None:
    with session_scope() as session:
        template = template_service.delete_template(
            session, product_id=product_id, template_id=template_id
        )
        typer.echo(f"Deleted template {template.id}")


@app.command("create-deployment")
def create_deployment(user_id: int, template_id: int, domainname: str) -> None:
    with session_scope() as session:
        try:
            deployment = deployment_service.create_deployment(
                session,
                payload=DeploymentCreate(
                    user_id=user_id, template_id=template_id, domainname=domainname
                ),
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Created deployment: {deployment}")


@app.command("list-deployments")
def list_deployments(user_id: int) -> None:
    with session_scope() as session:
        for deployment in deployment_service.list_deployments(session, user_id=user_id):
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
