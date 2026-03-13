from __future__ import annotations
from datetime import datetime
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    DeploymentCreate,
    DeploymentORM,
    DeploymentRead,
    ProductTemplateVersionORM,
    DeploymentUpdate,
)
from app.services.jobs import JobService
from app.services import template_values
from app.services import users as user_service
from app.services.errors import DeploymentInProgressException, IntegrityException, NotFoundException
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_DELETING,
    DEPLOYMENT_STATUS_PROVISIONING,
    JOB_REASON_CREATE,
    JOB_REASON_DELETE,
    JOB_REASON_UPDATE,
    DEPLOYMENT_STATUS_DELETED,
)
from app.services.reconcile_naming import generate_deployment_uid

logger = logging.getLogger(__name__)


def _enqueue_reconcile_job(session: Session, *, deployment_id: int, reason: str) -> None:
    logger.debug("Queueing reconcile job deployment_id=%s reason=%s", deployment_id, reason)
    JobService(session).enqueue_job(deployment_id=deployment_id, reason=reason)


def _get_deployment_orm(
    session: Session,
    *,
    deployment_id: int,
    user_id: int | None = None,
) -> DeploymentORM:
    stmt = select(DeploymentORM).where(DeploymentORM.id == deployment_id)
    if user_id is not None:
        stmt = stmt.where(DeploymentORM.user_id == user_id)
    if not (deployment := session.exec(stmt).one_or_none()):
        raise NotFoundException("Deployment not found")
    return deployment


def _validate_user_values(template: ProductTemplateVersionORM, user_values_json: dict[str, Any] | None) -> None:
    template_values.validate_user_values(user_values_json or {}, template.values_schema_json)


def _iter_hostname_paths(schema: Any, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    paths: list[tuple[str, ...]] = []
    if isinstance(schema, dict):
        title = schema.get("title")
        if path and isinstance(title, str) and title.lower() == "hostname":
            paths.append(path)

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if isinstance(key, str):
                    paths.extend(_iter_hostname_paths(child_schema, path + (key,)))

        items = schema.get("items")
        if isinstance(items, dict):
            paths.extend(_iter_hostname_paths(items, path + ("*",)))
        elif isinstance(items, list):
            for child_schema in items:
                paths.extend(_iter_hostname_paths(child_schema, path + ("*",)))

        for schema_key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            variants = schema.get(schema_key)
            if isinstance(variants, list):
                for child_schema in variants:
                    paths.extend(_iter_hostname_paths(child_schema, path))

        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            paths.extend(_iter_hostname_paths(additional, path))

        definitions = schema.get("$defs") or schema.get("definitions")
        if isinstance(definitions, dict):
            for child_schema in definitions.values():
                paths.extend(_iter_hostname_paths(child_schema, path))
    elif isinstance(schema, list):
        for child_schema in schema:
            paths.extend(_iter_hostname_paths(child_schema, path))
    return paths


def _value_for_path(user_values_json: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    current: Any = user_values_json or {}
    for key in path:
        if key == "*":
            if isinstance(current, list) and current:
                current = current[0]
                continue
            return None
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _derive_hostname(
    *,
    values_schema_json: dict[str, Any] | None,
    user_values_json: dict[str, Any] | None,
) -> str | None:
    if not isinstance(values_schema_json, dict):
        return None
    for path in _iter_hostname_paths(values_schema_json):
        value = _value_for_path(user_values_json, path)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)
    return None


def create_deployment(session: Session, *, payload: DeploymentCreate) -> DeploymentRead:
    # ensure that the user exists
    user = user_service.get_user(session, user_id=payload.user_id)
    # ensure that the template exists and retrieve it to validate product association
    template = session.get(ProductTemplateVersionORM, payload.desired_template_id)
    if not template:
        raise NotFoundException("Template not found")

    # Pre-flight the user-provided values against the template's schema:
    _validate_user_values(template, payload.user_values_json)
    derived_hostname = _derive_hostname(
        values_schema_json=template.values_schema_json,
        user_values_json=payload.user_values_json,
    )

    deployment_uid = generate_deployment_uid(product_name=template.product.name, user_email=user.email)
    deployment: DeploymentORM = DeploymentORM.model_validate(
        dict(
            deployment_uid=deployment_uid,
            hostname=derived_hostname,
            status=DEPLOYMENT_STATUS_PROVISIONING,
            **payload.model_dump(),
        )
    )
    session.add(deployment)
    try:
        session.flush()
        assert deployment.id is not None, "Deployment ID should not be None after flush"
        _enqueue_reconcile_job(session, deployment_id=deployment.id, reason=JOB_REASON_CREATE)
        session.commit()
        deployment = _get_deployment_orm(session, deployment_id=deployment.id)
        logger.info(
            "Created deployment id=%s user_id=%s desired_template_id=%s",
            deployment.id,
            deployment.user_id,
            deployment.desired_template_id,
        )
        return DeploymentRead.model_validate(deployment)
    except DeploymentInProgressException:
        session.rollback()
        logger.warning("Create deployment blocked by in-progress reconcile job for user_id=%s", payload.user_id)
        raise
    except IntegrityError as exc:
        session.rollback()
        logger.warning("Deployment create failed due to integrity conflict for user_id=%s", payload.user_id)
        raise IntegrityException("Deployment already exists") from exc


def list_deployments(session: Session, *, user_id: int | None = None) -> list[DeploymentRead]:
    # Return deployments for the given user if provided, otherwise all deployments
    stmt = select(DeploymentORM)
    if user_id is not None:
        stmt = stmt.where(DeploymentORM.user_id == user_id)  # noqa: E712
    return [DeploymentRead.model_validate(d) for d in session.exec(stmt).all()]


def get_deployment(session: Session, *, deployment_id: int, user_id: int | None = None) -> DeploymentRead:
    deployment = _get_deployment_orm(
        session,
        user_id=user_id,
        deployment_id=deployment_id,
    )
    return DeploymentRead.model_validate(deployment)


def delete_deployment(session: Session, *, user_id: int, deployment_id: int) -> DeploymentRead:
    """Mark a deployment as deleted.

    Retrieves the deployment ensuring it belongs to the given user. If not found,
    raises NotFoundException. Otherwise, sets the status to ``deleting`` and
    commits the transaction (the reconciler worker will perform the actual deletion).
    """
    deployment = _get_deployment_orm(session, user_id=user_id, deployment_id=deployment_id)
    if deployment.status not in (DEPLOYMENT_STATUS_DELETING, DEPLOYMENT_STATUS_DELETED):
        deployment.status = DEPLOYMENT_STATUS_DELETING
        deployment.generation += 1
        deployment.last_error = None
        deployment.deleted_at = datetime.utcnow()
        session.add(deployment)
        try:
            _enqueue_reconcile_job(session, deployment_id=deployment_id, reason=JOB_REASON_DELETE)
            session.commit()
        except DeploymentInProgressException:
            session.rollback()
            logger.warning("Delete deployment blocked by in-progress reconcile job deployment_id=%s", deployment_id)
            raise
        logger.info("Marked deployment id=%s user_id=%s for deletion", deployment_id, user_id)
    else:
        logger.info("Deployment id=%s user_id=%s is already marked for deletion or deleted", deployment_id, user_id)
    deployment = _get_deployment_orm(session, deployment_id=deployment_id)
    return DeploymentRead.model_validate(deployment)


def update_deployment(session: Session, update: DeploymentUpdate) -> DeploymentRead:
    deployment = _get_deployment_orm(
        session,
        user_id=update.user_id,
        deployment_id=update.id,
    )
    if update.desired_template_id <= deployment.desired_template_id:
        raise IntegrityException("Can only upgrade to newer versions, not downgrade")

    if not (target_template := session.get(ProductTemplateVersionORM, update.desired_template_id)):
        raise NotFoundException("Template not found")

    current_template = session.get(ProductTemplateVersionORM, deployment.desired_template_id)
    if current_template and target_template.product_id != current_template.product_id:
        raise IntegrityException("Upgrade template must belong to the same product")

    if update.user_values_json is not None:
        deployment.user_values_json = update.user_values_json

    # Pre-flight the user-provided values against the template's schema:
    _validate_user_values(target_template, deployment.user_values_json)
    deployment.hostname = _derive_hostname(
        values_schema_json=target_template.values_schema_json,
        user_values_json=deployment.user_values_json,
    )

    deployment.desired_template_id = update.desired_template_id
    deployment.status = DEPLOYMENT_STATUS_PROVISIONING
    deployment.generation += 1
    deployment.last_error = None
    session.add(deployment)
    try:
        _enqueue_reconcile_job(session, deployment_id=update.id, reason=JOB_REASON_UPDATE)
        session.commit()
    except DeploymentInProgressException:
        session.rollback()
        logger.warning("Update deployment blocked by in-progress reconcile job deployment_id=%s", update.id)
        raise
    deployment = _get_deployment_orm(session, deployment_id=update.id)
    logger.info(
        "Updated deployment id=%s user_id=%s desired_template_id=%s",
        deployment.id,
        deployment.user_id,
        deployment.desired_template_id,
    )
    return DeploymentRead.model_validate(deployment)
