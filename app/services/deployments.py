from __future__ import annotations

from sqlmodel import Session, select

from app.models import Deployment, ProductTemplateVersion, User
from app.provisioner import provisioner
from app.services.errors import NotFoundError


def create_deployment(
    session: Session, *, user_id: int, template_id: int, domainname: str
) -> Deployment:
    user = session.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")

    template = session.get(ProductTemplateVersion, template_id)
    if not template:
        raise NotFoundError("Template not found")

    deployment = Deployment(user_id=user_id, template_id=template_id, domainname=domainname)
    session.add(deployment)
    session.commit()
    session.refresh(deployment)

    provisioner.provision(deployment_id=deployment.id)
    return deployment


def list_deployments(session: Session, *, user_id: int) -> list[Deployment]:
    return list(
        session.exec(select(Deployment).where(Deployment.user_id == user_id)).all()
    )


def get_deployment(session: Session, *, user_id: int, deployment_id: int) -> Deployment:
    deployment = session.get(Deployment, deployment_id)
    if not deployment or deployment.user_id != user_id:
        raise NotFoundError("Deployment not found")
    return deployment
