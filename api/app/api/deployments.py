from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.deps import require_admin
from app.models import DeploymentRead, UserORM
from app.services import deployments as deployment_service

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get(
    "",
    response_model=list[DeploymentRead],
    summary="List all deployments across every user (admin)",
    response_description="A JSON array of every deployment across all users.",
    responses={
        200: {"description": "Every deployment across all users."},
        403: {"description": "Caller lacks administrator privileges."},
    },
)
def list_all_deployments(
    current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[DeploymentRead]:
    """Return every deployment across all users.

    This is the administrator-only counterpart to
    `GET /users/{user_id}/deployments`, which is scoped to a single user.

    ## Authorization
    Requires administrator privileges. Other callers receive **403 Forbidden**.

    ## Behavior
    Returns deployments belonging to any user. Each entry includes the owning
    user, along with its desired and applied template versions.

    ## Errors
    - **403 Forbidden** — the caller is not an administrator.
    """
    return deployment_service.list_deployments(session)
