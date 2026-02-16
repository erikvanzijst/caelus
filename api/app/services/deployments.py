from __future__ import annotations
from datetime import datetime
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models import DeploymentRead, DeploymentCreate, DeploymentORM, ProductTemplateVersionORM
from app.provisioner import provisioner
from app.services import users as user_service
from app.services.errors import IntegrityException, NotFoundException
from app.services.reconcile_naming import generate_deployment_uid


def create_deployment(session: Session, *, payload: DeploymentCreate) -> DeploymentRead:
    # ensure that the user exists
    user = user_service.get_user(session, user_id=payload.user_id)
    # ensure that the template exists and retrieve it to validate product association
    template = session.get(ProductTemplateVersionORM, payload.desired_template_id)
    if not template:
        raise NotFoundException("Template not found")
    deployment_uid = generate_deployment_uid(
        product_name=template.product.name,
        user_email=user.email)
    deployment: DeploymentORM = DeploymentORM.model_validate(dict(deployment_uid=deployment_uid, **payload.model_dump()))


    session.add(deployment)
    try:
        session.commit()
        session.refresh(deployment)
        # Ensure deployment.id is set
        assert deployment.id is not None, "Deployment ID should not be None after commit"
        provisioner.provision(deployment_id=cast(int, deployment.id))  # type: ignore
        return DeploymentRead.model_validate(deployment)
    except IntegrityError as exc:
        raise IntegrityException("Deployment already exists") from exc


def list_deployments(session: Session, *, user_id: int) -> list[DeploymentRead]:
    # Return deployments for the user that are not marked as deleted
    deployments = session.exec(
        select(DeploymentORM)
        .options(
            selectinload(DeploymentORM.user),
            selectinload(DeploymentORM.desired_template).selectinload(ProductTemplateVersionORM.product),
            selectinload(DeploymentORM.applied_template).selectinload(ProductTemplateVersionORM.product),
        )
        .where(DeploymentORM.user_id == user_id, DeploymentORM.deleted_at == None)  # noqa: E712
    ).all()
    # Convert ORM objects to read models
    return [DeploymentRead.model_validate(d) for d in deployments]


def get_deployment(session: Session, *, user_id: int, deployment_id: int) -> DeploymentRead:
    deployment = session.exec(
        select(DeploymentORM)
        .options(
            selectinload(DeploymentORM.user),
            selectinload(DeploymentORM.desired_template).selectinload(ProductTemplateVersionORM.product),
            selectinload(DeploymentORM.applied_template).selectinload(ProductTemplateVersionORM.product),
        )
        .where(DeploymentORM.deleted_at == None, DeploymentORM.id == deployment_id)
    ).one_or_none()
    if not deployment:
        raise NotFoundException("Deployment not found")
    return DeploymentRead.model_validate(deployment)


def delete_deployment(session: Session, *, user_id: int, deployment_id: int) -> DeploymentRead:
    """Mark a deployment as deleted.

    Retrieves the deployment ensuring it belongs to the given user. If not found,
    raises NotFoundException. Otherwise, sets the ``deleted`` flag to ``True`` and
    commits the transaction.
    """
    deployment = session.exec(
        select(DeploymentORM)
        .options(
            selectinload(DeploymentORM.user),
            selectinload(DeploymentORM.desired_template).selectinload(ProductTemplateVersionORM.product),
            selectinload(DeploymentORM.applied_template).selectinload(ProductTemplateVersionORM.product),
        )
        .where(DeploymentORM.id == deployment_id, DeploymentORM.deleted_at == None)
    ).one_or_none()
    if not deployment:
        raise NotFoundException("Deployment not found")
    deployment.deleted_at = datetime.utcnow()
    session.add(deployment)
    session.commit()
    return DeploymentRead.model_validate(deployment)
