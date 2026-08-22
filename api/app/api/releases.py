from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlmodel import Session

from app.db import get_session
from app.deps import require_self
from app.models import DeploymentReleaseWithBuildRead, UserORM
from app.services import deployments as deployment_service

router = APIRouter(
    prefix="/users/{user_id}/deployments/{deployment_id}/releases",
    tags=["releases"],
)


@router.get(
    "",
    response_model=list[DeploymentReleaseWithBuildRead],
    summary="List a deployment's releases",
    response_description="The deployment's releases, most recent first.",
    responses={
        200: {"description": "The deployment's releases, highest number first."},
        403: {"description": "Caller may only read their own deployments' releases."},
        404: {"description": "No such deployment exists for this user."},
    },
)
def list_releases(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> list[DeploymentReleaseWithBuildRead]:
    """List every rollout of a deployment, most recent first.

    ## Authorization
    You may only read your own deployments' releases; administrators may read
    any account's. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner of the deployment.
    - **deployment_id** — UUID of the deployment.

    ## Behavior
    Ordered by release number, highest first. Every release is listed whatever
    its outcome — `queued`, `in_flight`, `abandoned`, `failed` or `succeeded` —
    and each carries the build it shipped, inlined, or `null` where it names
    none.

    ## Errors
    - **403 Forbidden** — reading another account's releases without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user.
    """
    return deployment_service.list_releases(
        session,
        deployment_id=deployment_id,
        user_id=None if current_user.is_admin else user_id,
    )


@router.get(
    "/{number}",
    response_model=DeploymentReleaseWithBuildRead,
    summary="Get a single release",
    response_description="The release, with the build it shipped inlined.",
    responses={
        200: {"description": "The release."},
        403: {"description": "Caller may only read their own deployments' releases."},
        404: {"description": "No such deployment for this user, or no such release number."},
    },
)
def get_release(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment."),
    number: int = Path(
        ...,
        ge=1,
        description="The release's per-deployment number, as reported by the listing.",
    ),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> DeploymentReleaseWithBuildRead:
    """Retrieve one release of a deployment by its number.

    ## Authorization
    You may only read your own deployments' releases; administrators may read
    any account's. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner of the deployment.
    - **deployment_id** — UUID of the deployment.
    - **number** — the release's per-deployment number, starting at 1. This is
      the identifier releases are addressed by; the internal `uuid4` is never
      accepted here.

    ## Behavior
    Returns the release's intent (template, build, user values), its outcome
    (`error`, `helm_revision`), its timing, and its derived `status`. The build
    it shipped is inlined, or `null` where it names none.

    ## Errors
    - **403 Forbidden** — reading another account's releases without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user, or the
      deployment has no release with this number.
    """
    return deployment_service.get_release(
        session,
        deployment_id=deployment_id,
        number=number,
        user_id=None if current_user.is_admin else user_id,
    )
