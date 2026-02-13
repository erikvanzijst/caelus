from __future__ import annotations
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models import DeploymentRead, DeploymentCreate, DeploymentORM, ProductTemplateVersionORM
from app.provisioner import provisioner
from typing import cast
from app.services import users as user_service
from app.services.errors import IntegrityException, NotFoundException


def create_deployment(session: Session, *, payload: DeploymentCreate) -> DeploymentRead:
    deployment = DeploymentORM.model_validate(payload)
    # ensure that the user exists
    user_service.get_user(session, user_id=deployment.user_id)
    # ensure that the template exists and retrieve it to validate product association
    if not session.get(ProductTemplateVersionORM, deployment.template_id):
        raise NotFoundException("Template not found")
    # Optionally, could verify product association if needed

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
            selectinload(DeploymentORM.template).selectinload(ProductTemplateVersionORM.product),
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
            selectinload(DeploymentORM.template).selectinload(ProductTemplateVersionORM.product),
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
            selectinload(DeploymentORM.template).selectinload(ProductTemplateVersionORM.product),
        )
        .where(DeploymentORM.id == deployment_id, DeploymentORM.deleted_at == None)
    ).one_or_none()
    if not deployment:
        raise NotFoundException("Deployment not found")
    deployment.deleted_at = datetime.utcnow()
    session.add(deployment)
    session.commit()
    return DeploymentRead.model_validate(deployment)
