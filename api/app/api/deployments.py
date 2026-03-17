from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.deps import require_admin
from app.models import DeploymentRead, UserORM
from app.services import deployments as deployment_service

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get("", response_model=list[DeploymentRead])
def list_all_deployments(
    current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[DeploymentRead]:
    return deployment_service.list_deployments(session)
