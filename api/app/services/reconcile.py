from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from sqlmodel import Session

from app.models import DeploymentORM, ProductTemplateVersionORM, DeploymentRead
from app.provisioner import Provisioner, provisioner as default_provisioner
from app.services import template_values
from app.services.deployments import _get_deployment_orm
from app.services.errors import IntegrityException
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_DELETED,
    DEPLOYMENT_STATUS_ERROR,
    DEPLOYMENT_STATUS_READY,
)

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ReconcileResult:
    status: str
    applied_template_id: int | None
    last_error: str | None
    last_reconcile_at: datetime | None


class DeploymentReconciler:
    """Reconcile a single deployment state against Kubernetes/Helm."""

    def __init__(self, *, session: Session, provisioner: Provisioner | None = None) -> None:
        self._session = session
        self._provisioner = provisioner or default_provisioner

    def reconcile(self, deployment_id: int) -> ReconcileResult:
        logger.info("Starting reconcile for deployment_id=%s", deployment_id)
        deployment = _get_deployment_orm(self._session, deployment_id=deployment_id, include_deleted=True)
        try:
            self._validate_input_state(deployment)
            if deployment.deleted_at is not None:
                result = self._reconcile_delete(deployment)
            else:
                result = self._reconcile_apply(deployment)
        except Exception as exc:
            logger.exception("Reconcile failed for deployment_id=%s", deployment_id)
            result = ReconcileResult(
                status=DEPLOYMENT_STATUS_ERROR,
                applied_template_id=deployment.applied_template_id,
                last_error=str(exc),
                last_reconcile_at=datetime.utcnow(),
            )
        deployment.status = result.status
        deployment.applied_template_id = result.applied_template_id
        deployment.last_error = result.last_error
        deployment.last_reconcile_at = result.last_reconcile_at
        self._session.add(deployment)
        self._session.commit()
        self._session.refresh(deployment)
        logger.info(
            "Finished reconcile for deployment_id=%s status=%s applied_template_id=%s",
            deployment_id,
            result.status,
            result.applied_template_id,
        )
        return result

    @staticmethod
    def _validate_input_state(deployment: DeploymentORM) -> None:
        if not deployment.deployment_uid:
            raise IntegrityException("Deployment is missing deployment_uid")
        if deployment.user is None:
            raise IntegrityException("Deployment is missing loaded user relationship")
        if deployment.desired_template is None:
            raise IntegrityException("Deployment is missing loaded desired_template relationship")
        template = deployment.desired_template
        if template.deleted_at is not None:
            raise IntegrityException("Desired template is deleted")
        if template.chart_ref is None or template.chart_version is None:
            raise IntegrityException("Desired template chart_ref and chart_version are required")
        if template.product is None:
            raise IntegrityException("Desired template is missing loaded product relationship")

    def _reconcile_apply(self, deployment: DeploymentORM) -> ReconcileResult:
        template = deployment.desired_template
        assert template is not None
        release_name, namespace = self._resolve_identity(deployment)
        merged_values = self._build_merged_values(deployment, template)
        logger.debug(
            "Applying deployment_id=%s release=%s namespace=%s template_id=%s",
            deployment.id,
            release_name,
            namespace,
            deployment.desired_template_id,
        )

        self._provisioner.ensure_namespace(name=namespace)
        self._provisioner.helm_upgrade_install(
            release_name=release_name,
            namespace=namespace,
            chart_ref=template.chart_ref,
            chart_version=template.chart_version,
            chart_digest=template.chart_digest,
            values=merged_values,
            timeout=template.health_timeout_sec or 300,
            atomic=True,
            wait=True,
        )

        return ReconcileResult(
            status=DEPLOYMENT_STATUS_READY,
            applied_template_id=deployment.desired_template_id,
            last_error=None,
            last_reconcile_at=datetime.utcnow(),
        )

    def _reconcile_delete(self, deployment: DeploymentORM) -> ReconcileResult:
        release_name, namespace = self._resolve_identity(deployment)
        logger.debug(
            "Deleting deployment_id=%s release=%s namespace=%s",
            deployment.id,
            release_name,
            namespace,
        )
        timeout = (deployment.desired_template.health_timeout_sec or 300) if deployment.desired_template else 300

        self._provisioner.helm_uninstall(
            release_name=release_name,
            namespace=namespace,
            timeout=timeout,
            wait=True,
        )
        self._provisioner.delete_namespace(name=namespace)

        return ReconcileResult(
            status=DEPLOYMENT_STATUS_DELETED,
            applied_template_id=deployment.applied_template_id,
            last_error=None,
            last_reconcile_at=datetime.utcnow(),
        )

    @staticmethod
    def _resolve_identity(deployment: DeploymentORM) -> tuple[str, str]:
        identity = deployment.deployment_uid
        return identity, identity

    def _build_merged_values(
        self,
        deployment: DeploymentORM,
        template: ProductTemplateVersionORM,
    ) -> dict:
        template_values.validate_user_values(deployment.user_values_json, template.values_schema_json)
        merged_values = template_values.merge_values_scoped(
            template.default_values_json,
            deployment.user_values_json,
            self._build_system_overrides(deployment),
        )
        template_values.validate_merged_values(merged_values, template.values_schema_json)
        return merged_values

    def _build_system_overrides(self, deployment: DeploymentORM) -> dict:
        return {}
