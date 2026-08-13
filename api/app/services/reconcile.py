from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlmodel import Session

from app.config import get_settings
from app.models import DeploymentORM, ProductTemplateVersionORM, DeploymentRead
from app.provisioner import Provisioner, provisioner as default_provisioner
from app.services import template_values
from app.services.template_values import bytes_to_k8s_size
from app.services.deployments import _get_deployment_orm
from app.services.errors import IntegrityException
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_DELETED,
    DEPLOYMENT_STATUS_ERROR,
    DEPLOYMENT_STATUS_PENDING,
    DEPLOYMENT_STATUS_READY,
)

logger = logging.getLogger(__name__)

# Wall-clock budget handed to Helm for install/upgrade/uninstall waits. Chart
# readiness behavior is the chart's own concern, so this is a single
# platform-level timeout rather than a per-template knob.
HELM_TIMEOUT_SEC = 300


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

    def reconcile(self, deployment_id: UUID) -> ReconcileResult:
        logger.info("Starting reconcile for deployment_id=%s", deployment_id)
        deployment = _get_deployment_orm(self._session, deployment_id=deployment_id)
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
                last_reconcile_at=datetime.now(UTC),
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
        if deployment.status == DEPLOYMENT_STATUS_PENDING:
            raise IntegrityException("Deployment is awaiting payment and cannot be reconciled")
        if not deployment.name:
            raise IntegrityException("Deployment is missing name")
        if not deployment.namespace:
            raise IntegrityException("Deployment is missing namespace")
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
        merged_values = self._build_merged_values(deployment, template)
        logger.debug(
            "Applying deployment_id=%s release=%s namespace=%s template_id=%s",
            deployment.id,
            deployment.name,
            deployment.namespace,
            deployment.desired_template_id,
        )

        self._provisioner.ensure_namespace(name=deployment.namespace)
        self._provisioner.ensure_tenant_isolation(namespace=deployment.namespace)
        self._provisioner.helm_upgrade_install(
            release_name=deployment.name,
            namespace=deployment.namespace,
            chart_ref=template.chart_ref,
            chart_version=template.chart_version,
            chart_digest=template.chart_digest,
            values=merged_values,
            timeout=HELM_TIMEOUT_SEC,
            atomic=True,
            wait=True,
        )

        return ReconcileResult(
            status=DEPLOYMENT_STATUS_READY,
            applied_template_id=deployment.desired_template_id,
            last_error=None,
            last_reconcile_at=datetime.now(UTC),
        )

    def _reconcile_delete(self, deployment: DeploymentORM) -> ReconcileResult:
        logger.debug(
            "Deleting deployment_id=%s release=%s namespace=%s",
            deployment.id,
            deployment.name,
            deployment.namespace,
        )
        self._provisioner.helm_uninstall(
            release_name=deployment.name,
            namespace=deployment.namespace,
            timeout=HELM_TIMEOUT_SEC,
            wait=True,
        )
        self._provisioner.delete_namespace(name=deployment.namespace)

        return ReconcileResult(
            status=DEPLOYMENT_STATUS_DELETED,
            applied_template_id=deployment.applied_template_id,
            last_error=None,
            last_reconcile_at=datetime.now(UTC),
        )

    def _build_merged_values(
        self,
        deployment: DeploymentORM,
        template: ProductTemplateVersionORM,
    ) -> dict:
        template_values.validate_user_values(deployment.user_values_json, template.values_schema_json)
        system_overrides = self._build_system_overrides(deployment)
        return template_values.merge_values_scoped(
            template.system_values_json,
            deployment.user_values_json,
            system_overrides,
        )

    @classmethod
    def _build_system_overrides(cls, deployment: DeploymentORM) -> dict | None:
        """Combine all system-controlled value overrides under the ``caelus`` namespace.

        Each contributor returns a ``{"caelus": {...}}`` fragment; they are deep-merged
        so e.g. ``caelus.plan`` and ``caelus.ingress`` coexist. Returns ``None`` when nothing
        is contributed (preserving prior behaviour for plan-less, hostname-less releases).
        """
        overrides: dict = {}
        for part in (
            cls._build_plan_overrides(deployment),
            cls._build_ingress_overrides(deployment),
            cls._build_owner_overrides(deployment),
        ):
            if part:
                overrides = template_values.deep_merge(overrides, part)
        return overrides or None

    @staticmethod
    def _build_owner_overrides(deployment: DeploymentORM) -> dict | None:
        """Project the owning user's identity into the ``caelus.owner`` namespace.

        Fields are only included when present, and no block is emitted when neither
        is, so charts that require one fail loudly rather than rendering a blank.
        """
        user = getattr(deployment, "user", None)
        if user is None:
            return None
        owner: dict = {}
        email = getattr(user, "email", None)
        if email:
            owner["email"] = email
        user_id = getattr(user, "id", None)
        if user_id is not None:
            owner["id"] = user_id
        return {"caelus": {"owner": owner}} if owner else None

    @staticmethod
    def _build_ingress_overrides(deployment: DeploymentORM) -> dict | None:
        """Project system ingress + TLS settings into the ``caelus.ingress`` namespace.

        ``caelus.ingress.enabled`` marks that the platform exposes this deployment via an
        Ingress (true for any hostname-bearing deployment); ``caelus.ingress.host`` is the
        routing host and cert SAN. ``caelus.ingress.tls`` carries only the cert strategy:
        hosts under a configured wildcard domain (``*.freepod.eu``) are served by Traefik's
        default certificate store (``wildcard: true``, no per-app cert), while custom
        domains get a per-app HTTP-01 certificate via cert-manager (issuer + secret name
        injected here). Deployments without a hostname get no block at all.
        """
        hostname = deployment.hostname
        if not hostname:
            return None
        settings = get_settings()
        host = hostname.lower()
        is_wildcard = any(
            host == domain or host.endswith(f".{domain}")
            for domain in settings.wildcard_domains
        )
        tls: dict = {"wildcard": is_wildcard}
        if not is_wildcard:
            tls["issuer"] = settings.tls_cluster_issuer
            tls["secretName"] = f"{deployment.name}-tls"
        return {"caelus": {"ingress": {"enabled": True, "host": host, "tls": tls}}}

    @staticmethod
    def _build_plan_overrides(deployment: DeploymentORM) -> dict | None:
        """Project plan-level constraints into the caelus.plan Helm values namespace.

        Always injects ``caelus.plan`` when the deployment has a subscription so
        that chart templates using ``| default`` fail loudly if the key is
        unexpectedly absent (indicating a reconciler bug). Storage fields are
        only included when the plan defines a positive storage quota.
        """
        if not deployment.subscription or not deployment.subscription.plan_template:
            return None
        plan_values: dict = {}
        storage_bytes = deployment.subscription.plan_template.storage_bytes
        if storage_bytes:
            plan_values["storageBytes"] = storage_bytes
            plan_values["storageSize"] = bytes_to_k8s_size(storage_bytes)
        return {"caelus": {"plan": plan_values}}
