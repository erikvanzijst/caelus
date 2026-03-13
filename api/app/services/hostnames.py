from __future__ import annotations

import re
import socket
import logging

from sqlmodel import Session, select

from app.config import CaelusSettings, get_settings
from app.models import DeploymentORM
from app.services.errors import HostnameException
from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED

logger = logging.getLogger(__name__)

# RFC 952/1123: labels are 1-63 chars, alphanumeric + hyphens, no leading/trailing hyphens.
# Total FQDN max 253 chars.
_LABEL_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")


def _check_format(fqdn: str) -> None:
    if not fqdn or len(fqdn) > 253:
        raise HostnameException("invalid")
    labels = fqdn.rstrip(".").split(".")
    if len(labels) < 2:
        raise HostnameException("invalid")
    for label in labels:
        if not label or not _LABEL_RE.match(label):
            raise HostnameException("invalid")


def _check_reserved(fqdn: str, settings: CaelusSettings) -> None:
    if fqdn in settings.reserved_hostnames:
        raise HostnameException("reserved")


def _check_available(session: Session, fqdn: str, *, exclude_deployment_id: int | None = None) -> None:
    stmt = select(DeploymentORM.id).where(
        DeploymentORM.hostname == fqdn,
        DeploymentORM.status != DEPLOYMENT_STATUS_DELETED,
    )
    if exclude_deployment_id is not None:
        stmt = stmt.where(DeploymentORM.id != exclude_deployment_id)
    if session.exec(stmt).first() is not None:
        raise HostnameException("in_use")


def _check_resolving(fqdn: str, settings: CaelusSettings) -> None:
    if not settings.lb_ips:
        return

    lb_set = set(settings.lb_ips)
    try:
        results = socket.getaddrinfo(fqdn, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise HostnameException("not_resolving")

    resolved_ips = {addr[0] for _, _, _, _, addr in results}
    if not resolved_ips or not resolved_ips <= lb_set:
        raise HostnameException("not_resolving")


def require_valid_hostname_for_deployment(
    session: Session,
    fqdn: str,
    *,
    exclude_deployment_id: int | None = None,
    settings: CaelusSettings | None = None,
) -> None:
    """Validate that *fqdn* can be used for a new or updated deployment.

    Raises ``HostnameException(reason=...)`` on the first failing check.
    Checks run in order: format → reserved → availability → DNS resolution.

    Pass *exclude_deployment_id* when updating an existing deployment so its
    own hostname doesn't trigger an "in_use" conflict.
    """
    settings = settings or get_settings()
    _check_format(fqdn)
    _check_reserved(fqdn, settings)
    _check_available(session, fqdn, exclude_deployment_id=exclude_deployment_id)
    _check_resolving(fqdn, settings)
