from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user, get_payment_provider, require_admin, require_self
from app.models import (
    DeploymentCreate,
    DeploymentCreateResponse,
    DeploymentRead,
    SftpCredentialsRead,
    TosAcceptanceCreate,
    TosAcceptanceRead,
    UserORM,
    UserRead, DeploymentUpdate,
)
from app.services import deployments as deployment_service, users as user_service
from app.services.mollie import PaymentProvider
from app.util import amend_url

router = APIRouter(prefix="/users", tags=["users"])

me_router = APIRouter(tags=["users"])


@me_router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current authenticated user",
    response_description="The authenticated caller's own user record.",
)
def get_me(current_user: UserORM = Depends(get_current_user)) -> UserRead:
    """Return the profile of the currently authenticated caller.

    Includes the caller's `id` — needed to build every `/users/{user_id}/...`
    request — and whether they are an administrator.

    ## Authorization
    Requires authentication. Returns the authenticated caller's own record;
    there is no admin or self restriction.

    ## Behavior
    The first time a given account calls the API, its user record is created
    automatically; subsequent calls return the existing record. Email matching
    is case-insensitive.
    """
    return UserRead.model_validate(current_user)


@me_router.get(
    "/me/tos-acceptance",
    response_model=TosAcceptanceRead,
    summary="Get the current user's Terms of Service acceptance",
    response_description="The caller's ToS acceptance status; `version` is null "
    "if they have not accepted.",
)
def get_my_tos_acceptance(
    current_user: UserORM = Depends(get_current_user),
) -> TosAcceptanceRead:
    """Return whether — and which version of — the Terms of Service the caller
    has accepted.

    This is always readable and returns **200** even when the caller has not yet
    accepted (in which case `version` and `accepted_at` are null), so clients can
    treat "not accepted" as a normal state rather than a 404.
    """
    return user_service.get_tos_acceptance(current_user)


@me_router.post(
    "/me/tos-acceptance",
    response_model=TosAcceptanceRead,
    summary="Record the current user's Terms of Service acceptance",
    response_description="The updated ToS acceptance status.",
    responses={
        409: {"description": "The submitted version is not the current Terms of "
                             "Service version (the terms have changed)."},
        422: {"description": "The submitted version is not a well-formed date."},
    },
)
def record_my_tos_acceptance(
    payload: TosAcceptanceCreate,
    current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> TosAcceptanceRead:
    """Record the caller's acceptance of the current Terms of Service.

    The submitted `version` MUST equal the current ToS version; a mismatch is
    rejected with **409** (the terms changed under the user, who must re-review).
    Recording is idempotent for the current version.
    """
    return user_service.record_tos_acceptance(
        session, user=current_user, version=payload.version
    )


@router.get("", response_model=list[UserRead])
def list_users(
    current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[UserRead]:
    """List every user.

    ## Authorization
    Requires administrator privileges. Other callers receive `403 Forbidden`.

    ## Errors
    - **403 Forbidden** — the caller is not an administrator.
    """
    return user_service.list_users(session)


@router.delete(
    "/{user_id}",
    status_code=501,
    summary="Delete a user (not implemented)",
    response_description="This endpoint always fails; it returns no body.",
    responses={
        501: {"description": "User deletion is not yet implemented."},
    },
)
def delete_user_endpoint(
    user_id: int = Path(..., description="ID of the user to delete."),
    current_user: UserORM = Depends(get_current_user),
) -> None:
    """Delete a user — **not yet implemented**.

    This route is a deliberate stub reserving the URL; it always raises
    `501 Not Implemented` and performs no deletion.

    ## Authorization
    Requires authentication. No further authorization is enforced because the
    handler always returns `501` before doing any work.

    ## Parameters
    - **user_id** — the user that would be deleted (currently ignored).

    ## Errors
    - **501 Not Implemented** — always, since deletion is unimplemented.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User deletion is not yet implemented",
    )


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Get a single user",
    response_description="The requested user record.",
    responses={
        403: {"description": "Caller may only access their own account."},
        404: {"description": "No user exists with this id."},
    },
)
def get_user(
    user_id: int = Path(..., description="ID of the user to retrieve."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> UserRead:
    """Retrieve a single user by id.

    ## Authorization
    You may only retrieve your own account (`user_id` must be your own);
    administrators may retrieve any account. Other requests receive
    `403 Forbidden`.

    ## Parameters
    - **user_id** — the user to retrieve.

    ## Errors
    - **403 Forbidden** — attempting to access another account without
      administrator privileges.
    - **404 Not Found** — no user exists with this id.
    """
    return user_service.get_user(session, user_id=user_id)


@router.post(
    "/{user_id}/deployments",
    response_model=DeploymentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a deployment for a user",
    response_description=(
        "Envelope with the newly created deployment and, for paid plans, a "
        "`checkout_url` the client must redirect the user to."
    ),
    responses={
        400: {"description": "`user_values_json` fails validation against the template schema, or the plan template is invalid."},
        403: {"description": "Caller may only create deployments for their own account."},
        404: {"description": "The user or desired template does not exist."},
        409: {"description": "The desired template is not the product's current version, the chosen hostname is already in use, an operation is already in progress, or a duplicate deployment exists."},
    },
)
def create_deployment(
    user_id: int = Path(..., description="ID of the user that will own the deployment."),
    payload: DeploymentCreate = ...,
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
    payment_provider: PaymentProvider | None = Depends(get_payment_provider),
) -> DeploymentCreateResponse:
    """Provision a new deployment (product instance) for ``user_id``.

    Depending on the plan, provisioning either starts immediately (free plans)
    or begins once payment succeeds (paid plans).

    ## Authorization
    You may only create deployments for your own account (`user_id` must be your
    own); administrators may create deployments for any account. Other requests
    receive `403 Forbidden`.

    ## Parameters
    - **user_id** (path) — owner of the new deployment. This value is written
      onto `payload.user_id`, **overriding** whatever the request body carried.
    - **payload.desired_template_id** — the product template version the request
      was built against. Must be the product's current template version.
    - **payload.plan_template_id** — the selected plan template version; must
      belong to the same product. Determines pricing.
    - **payload.user_values_json** — user-supplied configuration, validated
      against the template's `values_schema_json`. The field titled `hostname`
      (case-insensitive), if present, is normalized to lowercase and used as the
      deployment hostname.

    ## Behavior
    - The deployment's `name` is generated server-side and cannot be set by the
      client.
    - **Free plan** (`price_cents == 0`, or when payment is not enabled): the
      deployment is created in the `provisioning` state, provisioning begins
      immediately, and `checkout_url` is `null`.
    - **Paid plan** (`price_cents > 0` and payment is enabled): the deployment
      is created in the `pending` state and the response `checkout_url` points
      at the payment page; provisioning begins once payment succeeds.

    ## Errors
    - **400 Bad Request** — `user_values_json` fails schema validation, or the
      plan template is invalid.
    - **403 Forbidden** — creating a deployment for another account without
      administrator privileges.
    - **404 Not Found** — the user or desired template does not exist.
    - **409 Conflict** — the desired template is not the product's current
      version, the chosen hostname is already in use, an operation is already in
      progress, or a duplicate deployment already exists.
    """
    payload.user_id = user_id
    result = deployment_service.create_deployment(
        session,
        payload=payload,
        payment_provider=payment_provider,
    )
    return DeploymentCreateResponse(
        deployment=result.deployment,
        checkout_url=result.checkout_url,
    )


@router.get(
    "/{user_id}/deployments",
    response_model=list[DeploymentRead],
    summary="List a user's deployments",
    response_description="The user's deployments.",
    responses={
        403: {"description": "Caller may only list their own deployments."},
    },
)
def list_deployments(
    user_id: int = Path(..., description="ID of the user whose deployments to list."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
):
    """List all deployments owned by ``user_id``.

    ## Authorization
    You may only list your own deployments; administrators may list any account's
    deployments. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner whose deployments are listed.

    ## Behavior
    An unknown user id simply returns an empty array (no `404`).

    ## Errors
    - **403 Forbidden** — listing another account's deployments without
      administrator privileges.
    """
    return deployment_service.list_deployments(session, user_id=user_id)


@router.get(
    "/{user_id}/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Get a single deployment",
    response_description="The requested deployment, including status and hostname.",
    responses={
        403: {"description": "Caller may only access their own deployments."},
        404: {"description": "No such deployment exists for this user."},
    },
)
def get_deployment(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment to retrieve."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> DeploymentRead:
    """Retrieve a single deployment owned by ``user_id``.

    ## Authorization
    You may only access your own deployments; administrators may access any
    account's deployments. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner of the deployment.
    - **deployment_id** — UUID of the deployment.

    ## Behavior
    A deployment that does not belong to `user_id` is reported as `404`.

    ## Errors
    - **403 Forbidden** — accessing another account's deployment without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user.
    """
    return deployment_service.get_deployment(session, user_id=user_id, deployment_id=deployment_id)


@router.get(
    "/{user_id}/deployments/{deployment_id}/sftp",
    response_model=SftpCredentialsRead,
    summary="Get a deployment's SFTP credentials",
    response_description="SFTP host, port, username and password for file access.",
    responses={
        403: {"description": "Caller may only access their own deployments."},
        404: {"description": "No such deployment exists for this user, or the deployment provides no SFTP file access."},
    },
)
def get_deployment_sftp(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment whose SFTP credentials to fetch."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> SftpCredentialsRead:
    """Return the SFTP connection details for a deployment that offers file access.

    A `404` indicates the deployment's product does not offer SFTP file access.

    ## Authorization
    You may only access your own deployments; administrators may access any
    account's deployments. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner of the deployment.
    - **deployment_id** — UUID of the deployment.

    ## Behavior
    The response provides the `host`, `port`, `username`, and `password` for
    connecting to the deployment's file storage over SFTP. A `404` is returned
    when no such deployment exists for this user, or when the deployment's
    product does not offer SFTP file access.

    ## Errors
    - **403 Forbidden** — accessing another account's deployment without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user, or SFTP
      access is not available for this deployment.
    """
    return deployment_service.get_sftp_credentials(
        session, user_id=user_id, deployment_id=deployment_id
    )


@router.put(
    "/{user_id}/deployments/{deployment_id}",
    response_model=DeploymentRead,
    summary="Update (upgrade) a deployment",
    response_description="The updated deployment, now re-entering provisioning.",
    responses={
        400: {"description": "`user_values_json` fails validation against the target template schema."},
        403: {"description": "Caller may only update their own deployments."},
        404: {"description": "No such deployment exists for this user, or the target template does not exist."},
        409: {"description": "Downgrade attempt, cross-product template, an operation is already in progress, or the deployment is not in a ready/error state."},
    },
)
def update_deployment(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment to update."),
    deployment: DeploymentUpdate = ...,
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> DeploymentRead:
    """Update a deployment, typically to upgrade its template version.

    ## Authorization
    You may only update your own deployments; administrators may update any
    account's deployments. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** (path) — owner of the deployment. Written onto
      `deployment.user_id`, **overriding** any value in the body.
    - **deployment_id** (path) — UUID of the deployment. Written onto
      `deployment.id`, **overriding** any value in the body.
    - **deployment.desired_template_id** — the template version to move to. Must
      be greater than or equal to the current version (upgrades only) and belong
      to the same product.
    - **deployment.user_values_json** — new configuration; when omitted the
      existing stored values are reused. When provided it is validated against
      the target template schema, and the `hostname`-titled field is re-derived.

    ## Behavior
    The update is accepted only when the deployment is currently in the `ready`
    or `error` state; the deployment then returns to the `provisioning` state
    while the change is applied.

    ## Errors
    - **400 Bad Request** — the effective `user_values_json` fails schema
      validation.
    - **403 Forbidden** — updating another account's deployment without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user, or the target
      template does not exist.
    - **409 Conflict** — the target version is older than the current one, the
      target template belongs to a different product, an operation is already in
      progress, or the deployment is not in a `ready`/`error` state.
    """
    deployment.user_id = user_id
    deployment.id = deployment_id
    return deployment_service.update_deployment(session, deployment)


@router.delete(
    "/{user_id}/deployments/{deployment_id}",
    status_code=204,
    summary="Delete a deployment",
    response_description="Empty body; the deployment is scheduled for teardown.",
    responses={
        403: {"description": "Caller may only delete their own deployments."},
        404: {"description": "No such deployment exists for this user."},
        409: {"description": "An operation is already in progress for this deployment."},
    },
)
def delete_deployment_endpoint(
    user_id: int = Path(..., description="ID of the user that owns the deployment."),
    deployment_id: UUID = Path(..., description="UUID of the deployment to delete."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> None:
    """Schedule a deployment for deletion.

    ## Authorization
    You may only delete your own deployments; administrators may delete any
    account's deployments. Other requests receive `403 Forbidden`.

    ## Parameters
    - **user_id** — owner of the deployment.
    - **deployment_id** — UUID of the deployment to delete.

    ## Behavior
    Deletion is asynchronous: the deployment enters the `deleting` state and its
    teardown proceeds in the background. The call is idempotent — deleting a
    deployment that is already being deleted still returns `204`. Returns no
    body.

    ## Errors
    - **403 Forbidden** — deleting another account's deployment without
      administrator privileges.
    - **404 Not Found** — no such deployment exists for this user.
    - **409 Conflict** — an operation is already in progress for this deployment.
    """
    deployment_service.delete_deployment(session, user_id=user_id, deployment_id=deployment_id)
