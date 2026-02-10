from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import DeploymentRead, DeploymentCreate, DeploymentORM
from app.provisioner import provisioner
from app.services import users as user_service, templates as template_service
from app.services.errors import IntegrityException, NotFoundException


def create_deployment(session: Session, *, payload: DeploymentCreate) -> DeploymentRead:
    deployment = DeploymentORM.model_validate(payload)
    # ensure that the user and template exist:
    user_service.get_user(session, user_id=deployment.user_id)
    template_service.get_template(session, product_id=deployment.template_id, template_id=deployment.template_id)

    session.add(deployment)
    try:
        session.commit()
        session.refresh(deployment)

        provisioner.provision(deployment_id=deployment.id)
        return DeploymentRead.model_validate(deployment)
    except IntegrityError as exc:
        raise IntegrityException(f"Deployment already exists") from exc


def list_deployments(session: Session, *, user_id: int) -> list[DeploymentRead]:
    # TODO: filter out deleted deployments and convert to list[DeploymentRead]
    return list(
        session.exec(select(DeploymentORM).where(DeploymentORM.user_id == user_id)).all()
    )


def get_deployment(session: Session, *, user_id: int, deployment_id: int) -> DeploymentRead:
    deployment = session.get(DeploymentORM, deployment_id)
    if not deployment or deployment.user_id != user_id:
        raise NotFoundException("Deployment not found")
    return DeploymentRead.model_validate(deployment)

# TODO: delete deployment
