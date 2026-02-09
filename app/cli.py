from __future__ import annotations

import typer

from app.db import session_scope
from app.services import deployments as deployment_service
from app.services import products as product_service
from app.services import templates as template_service
from app.services import users as user_service
from app.services.errors import NotFoundError

app = typer.Typer(help="Caelus CLI")


@app.command("create-user")
def create_user(email: str) -> None:
    with session_scope() as session:
        user = user_service.create_user(session, email=email)
        typer.echo(f"Created user {user.id} ({user.email})")


@app.command("list-users")
def list_users() -> None:
    with session_scope() as session:
        for user in user_service.list_users(session):
            typer.echo(f"{user.id} {user.email} {user.created_at}")


@app.command("create-product")
def create_product(name: str, description: str, template: str = "") -> None:
    with session_scope() as session:
        product = product_service.create_product(
            session, name=name, description=description, template=template or None
        )
        typer.echo(f"Created product {product.id} ({product.name})")


@app.command("list-products")
def list_products() -> None:
    with session_scope() as session:
        for product in product_service.list_products(session):
            typer.echo(f"{product.id} {product.name} deleted={product.deleted}")


@app.command("create-template")
def create_template(product_id: int, docker_image_url: str = "") -> None:
    with session_scope() as session:
        try:
            template = template_service.create_template(
                session, product_id=product_id, docker_image_url=docker_image_url or None
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Created template {template.id} for product {product_id}")


@app.command("list-templates")
def list_templates(product_id: int) -> None:
    with session_scope() as session:
        for template in template_service.list_templates(session, product_id=product_id):
            typer.echo(f"{template.id} product={template.product_id} image={template.docker_image_url}")


@app.command("create-deployment")
def create_deployment(user_id: int, template_id: int, domainname: str) -> None:
    with session_scope() as session:
        try:
            deployment = deployment_service.create_deployment(
                session, user_id=user_id, template_id=template_id, domainname=domainname
            )
        except NotFoundError:
            raise typer.Exit(code=1)
        typer.echo(f"Created deployment {deployment.id} for {domainname}")


@app.command("list-deployments")
def list_deployments(user_id: int) -> None:
    with session_scope() as session:
        for deployment in deployment_service.list_deployments(session, user_id=user_id):
            typer.echo(
                f"{deployment.id} user={deployment.user_id} template={deployment.template_id} {deployment.domainname}"
            )


if __name__ == "__main__":
    app()
