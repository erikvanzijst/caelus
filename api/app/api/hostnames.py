from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_user
from app.models import UserORM
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
    current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> HostnameCheck:
    try:
        require_valid_hostname_for_deployment(session, fqdn)
        return HostnameCheck(fqdn=fqdn, usable=True)
    except HostnameException as exc:
        return HostnameCheck(fqdn=fqdn, usable=False, reason=exc.reason)
