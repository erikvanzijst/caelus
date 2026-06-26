from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.services.errors import HostnameException
from app.services.hostnames import require_valid_hostname_for_deployment

router = APIRouter(tags=["hostnames"])


class HostnameCheck(BaseModel):
    fqdn: str
    usable: bool
    reason: str | None = None


@router.get("/hostnames/{fqdn}", response_model=HostnameCheck)
def check_hostname(
    fqdn: str,
    # Intentionally unauthenticated: the response (usable/reason) carries nothing
    # sensitive and the field validates hostnames as the user types, before any
    # deployment exists. See `list_domains` below, which is public for the same
    # reason.
    #
    # Note: validation performs outbound DNS lookups to caller-controlled
    # authoritative nameservers (see _check_cname), each able to hold a worker
    # for up to the resolver lifetime. Being unauthenticated, this is in
    # principle a DoS / DNS-amplification handle. Accepted as low risk: the cost
    # per request is small, and the same vector is reachable by any authenticated
    # user anyway, so auth was never a real mitigation. Add a per-IP rate limit
    # here if abuse ever materializes.
    session: Session = Depends(get_session),
) -> HostnameCheck:
    fqdn = fqdn.lower()
    try:
        require_valid_hostname_for_deployment(session, fqdn)
        return HostnameCheck(fqdn=fqdn, usable=True)
    except HostnameException as exc:
        return HostnameCheck(fqdn=fqdn, usable=False, reason=exc.reason)


@router.get("/domains", response_model=list[str])
def list_domains() -> list[str]:
    return get_settings().wildcard_domains


@router.get("/cname-target", response_model=str)
def cname_target() -> str:
    """The platform domain that custom hostnames must CNAME to.

    Differs per environment (e.g. ``freepod.eu`` in prod, ``dev.freepod.eu`` in
    dev). Empty string when unconfigured. Public for the same reasons as
    ``check_hostname``."""
    return get_settings().domain
