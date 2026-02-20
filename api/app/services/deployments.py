from __future__ import annotations
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models import (
    DeploymentCreate,
    DeploymentORM,
    DeploymentRead,
    ProductTemplateVersionORM, DeploymentUpdate,
)
from app.services import jobs as jobs_service
from app.services import template_values
from app.services import users as user_service
from app.services.errors import DeploymentInProgressException, IntegrityException, NotFoundException
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_DELETING,
    DEPLOYMENT_STATUS_PENDING,
    DEPLOYMENT_STATUS_UPGRADING,
    JOB_REASON_CREATE,
    JOB_REASON_DELETE,
    JOB_REASON_UPDATE,
)
from app.services.reconcile_naming import generate_deployment_uid


def _enqueue_reconcile_job(session: Session, *, deployment_id: int, reason: str) -> None:
    jobs_service.enqueue_job(session, deployment_id=deployment_id, reason=reason)


def _get_active_deployment_orm(
    session: Session,
    *,
    user_id: int,
    deployment_id: int,
) -> DeploymentORM:
    deployment = session.exec(
        select(DeploymentORM)
        .options(
            selectinload(DeploymentORM.user),
            selectinload(DeploymentORM.desired_template).selectinload(ProductTemplateVersionORM.product),
            selectinload(DeploymentORM.applied_template).selectinload(ProductTemplateVersionORM.product),
        )
        .where(
            DeploymentORM.deleted_at == None,  # noqa: E712
            DeploymentORM.user_id == user_id,
            DeploymentORM.id == deployment_id,
        )
    ).one_or_none()
    if not deployment:
        raise NotFoundException("Deployment not found")
    return deployment


def _validate_user_values(template: ProductTemplateVersionORM, user_values_json: dict | None) -> None:
    template_values.validate_user_values(user_values_json, template.values_schema_json)
    merged_values = template_values.merge_values_scoped(
        template.default_values_json,
        user_values_json,
        system_overrides={},
    )
    template_values.validate_merged_values(merged_values, template.values_schema_json)


def create_deployment(session: Session, *, payload: DeploymentCreate) -> DeploymentRead:
    # ensure that the user exists
    user = user_service.get_user(session, user_id=payload.user_id)
    # ensure that the template exists and retrieve it to validate product association
    template = session.get(ProductTemplateVersionORM, payload.desired_template_id)
    if not template:
        raise NotFoundException("Template not found")

    # Pre-flight the user-provided values against the template's schema:
    _validate_user_values(template, payload.user_values_json)

    deployment_uid = generate_deployment_uid(product_name=template.product.name, user_email=user.email)
    deployment: DeploymentORM = DeploymentORM.model_validate(
        dict(
            deployment_uid=deployment_uid,
            status=DEPLOYMENT_STATUS_PENDING,
            **payload.model_dump(),
        )
    )
    session.add(deployment)
    try:
        session.flush()
        assert deployment.id is not None, "Deployment ID should not be None after flush"
        _enqueue_reconcile_job(session, deployment_id=deployment.id, reason=JOB_REASON_CREATE)
        session.commit()
        session.refresh(deployment)
        return DeploymentRead.model_validate(deployment)
    except DeploymentInProgressException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
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
    deployment = _get_active_deployment_orm(session, user_id=user_id, deployment_id=deployment_id)
    return DeploymentRead.model_validate(deployment)


def delete_deployment(session: Session, *, user_id: int, deployment_id: int) -> DeploymentRead:
    """Mark a deployment as deleted.

    Retrieves the deployment ensuring it belongs to the given user. If not found,
    raises NotFoundException. Otherwise, sets the ``deleted`` flag to ``True`` and
    commits the transaction.
    """
    deployment = _get_active_deployment_orm(session, user_id=user_id, deployment_id=deployment_id)
    deployment.status = DEPLOYMENT_STATUS_DELETING
    deployment.generation += 1
    deployment.last_error = None

    # TODO: this makes the deployment invisible to the user immediately (undesireable --
    #  should probably only toggle the flag after the instance has been deleted successfully):
    deployment.deleted_at = datetime.utcnow()
    session.add(deployment)
    try:
        _enqueue_reconcile_job(session, deployment_id=deployment_id, reason=JOB_REASON_DELETE)
        session.commit()
    except DeploymentInProgressException:
        session.rollback()
        raise
    return DeploymentRead.model_validate(deployment)


def update_deployment(session: Session, update: DeploymentUpdate) -> DeploymentRead:
    deployment = _get_active_deployment_orm(session, user_id=update.user_id, deployment_id=update.id)
    if update.desired_template_id <= deployment.desired_template_id:
        raise IntegrityException("Can only upgrade to newer versions, not downgrade")

    if not (target_template := session.get(ProductTemplateVersionORM, update.desired_template_id)):
        raise NotFoundException("Template not found")

    current_template = session.get(ProductTemplateVersionORM, deployment.desired_template_id)
    if current_template and target_template.product_id != current_template.product_id:
        raise IntegrityException("Upgrade template must belong to the same product")

    # Pre-flight the user-provided values against the template's schema:
    _validate_user_values(target_template, deployment.user_values_json)

    deployment.desired_template_id = update.desired_template_id
    deployment.status = DEPLOYMENT_STATUS_UPGRADING
    deployment.generation += 1
    deployment.last_error = None
    session.add(deployment)
    try:
        _enqueue_reconcile_job(session, deployment_id=update.id, reason=JOB_REASON_UPDATE)
        session.commit()
    except DeploymentInProgressException:
        session.rollback()
        raise
    session.refresh(deployment)
    return DeploymentRead.model_validate(deployment)
