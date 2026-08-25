from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import (
    PlanCreate,
    PlanRead,
    PlanTemplateVersionCreate,
    PlanTemplateVersionRead,
    PlanUpdate,
    UserORM,
)
from app.services import plans as plan_service

router = APIRouter(tags=["plans"])


# ---------------------------------------------------------------------------
# Plan browsing (any authenticated user)
# ---------------------------------------------------------------------------


@router.get(
    "/products/{product_id}/plans",
    response_model=list[PlanRead],
    summary="List plans for a product",
    response_description=(
        "The product's plans, each with its current template-version pricing "
        "details."
    ),
    responses={404: {"description": "No product exists with this id."}},
)
def list_plans(
    product_id: int = Path(..., description="ID of the product whose plans to list."),
    session: Session = Depends(get_session),
) -> list[PlanRead]:
    """List the plans available for a product.

    Plans are returned ordered by ``sort_order`` (ascending) and then by ``id``.
    Each plan embeds its current template version (``template``), which carries
    the price, billing interval, storage and database quotas, and description.

    ## Authorization
    Public — no authentication required.

    ## Parameters
    - **product_id** (path) — the product whose plans are listed.

    ## Behavior
    - The product must exist; otherwise the request fails with 404.
    - A product with no plans yields an empty array (not a 404).
    - A plan that has no template version yet is returned with ``template`` set
      to ``null``.

    ## Errors
    - **404 Not Found** — no product exists with this id.
    """
    return plan_service.list_plans_for_product(session, product_id)


@router.get(
    "/plans/{plan_id}",
    response_model=PlanRead,
    summary="Get a plan",
    response_description=(
        "The plan and its current template-version pricing details."
    ),
    responses={404: {"description": "No plan exists with this id."}},
)
def get_plan(
    plan_id: int = Path(..., description="ID of the plan to retrieve."),
    session: Session = Depends(get_session),
) -> PlanRead:
    """Fetch a single plan by id, including its current template version.

    The embedded ``template`` (when present) supplies the plan's commercial
    terms: ``price_cents`` (``0`` denotes a free plan), ``billing_interval``
    (``monthly`` or ``annual``), ``storage_bytes``, ``database_bytes`` and a
    Markdown ``description``.

    ## Authorization
    Public — no authentication required.

    ## Parameters
    - **plan_id** (path) — the plan to retrieve.

    ## Behavior
    - When the plan has no template version yet, ``template`` is ``null``.

    ## Errors
    - **404 Not Found** — no plan exists with this id.
    """
    return plan_service.get_plan(session, plan_id)


# ---------------------------------------------------------------------------
# Plan administration (admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/products/{product_id}/plans",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a plan (admin only)",
    response_description="The newly created plan (with `template` set to null).",
    responses={
        201: {"description": "The plan was created."},
        403: {"description": "The caller lacks administrator privileges."},
        404: {"description": "No product exists with this id."},
        409: {
            "description": (
                "A plan with this name already exists for the product "
                "(case-insensitive)."
            )
        },
    },
)
def create_plan(
    product_id: int = Path(
        ..., description="ID of the product the plan belongs to (taken from the path)."
    ),
    payload: PlanCreate = ...,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanRead:
    """Create a new plan for a product.

    A freshly created plan has no template version yet, so the response
    ``template`` field is ``null``. Commercial terms are added afterwards via
    ``POST /plans/{plan_id}/templates``.

    ## Authorization
    Requires administrator privileges. Other callers receive `403 Forbidden`.

    ## Parameters
    - **product_id** (path) — the owning product. This value is authoritative:
      the plan's ``product_id`` is always taken from the path, not the body.
    - **name** (body, required) — the plan display name; must be unique per
      product (case-insensitive).
    - **sort_order** (body, optional) — integer used to order plans within the
      product.

    ## Behavior
    - The product must exist; otherwise 404.
    - A plan name that collides with an existing plan of the same product
      yields 409.

    ## Errors
    - **404 Not Found** — the product does not exist.
    - **403 Forbidden** — the caller is not an administrator.
    - **409 Conflict** — a plan with this name already exists for the product.
    """
    return plan_service.create_plan(session, product_id=product_id, payload=payload)


@router.put(
    "/plans/{plan_id}",
    response_model=PlanRead,
    summary="Update a plan (admin only)",
    response_description="The updated plan with its (possibly changed) canonical template.",
    responses={
        403: {"description": "The caller lacks administrator privileges."},
        404: {
            "description": (
                "No plan exists with this id, or the supplied `template_id` is "
                "unknown or belongs to another plan."
            )
        },
        409: {
            "description": (
                "The new name conflicts with another plan of the same product."
            )
        },
    },
)
def update_plan(
    plan_id: int = Path(..., description="ID of the plan to update."),
    payload: PlanUpdate = ...,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanRead:
    """Update a plan's mutable fields.

    Only display/ordering and the current-template selection are mutable; a
    plan's commercial terms are never edited in place (they live on separate,
    immutable template versions). Changing ``template_id`` points the plan at a
    new set of terms for new subscribers; existing subscriptions keep the terms
    they were sold at and are unaffected.

    ## Authorization
    Requires administrator privileges. Other callers receive `403 Forbidden`.

    ## Parameters
    - **plan_id** (path) — the plan to update.
    - **name** (body, optional) — new display name; must stay unique per product
      (case-insensitive).
    - **template_id** (body, optional) — id of a template version to select as
      the plan's current terms. It must exist and belong to this plan.
    - **sort_order** (body, optional) — new ordering value.

    All body fields are optional; only the provided fields are applied.

    ## Behavior
    - The plan must exist; otherwise 404.
    - A ``template_id`` that is unknown or belongs to a different plan is
      rejected with 404.

    ## Errors
    - **404 Not Found** — the plan does not exist, or ``template_id`` is unknown
      / does not belong to this plan.
    - **403 Forbidden** — the caller is not an administrator.
    - **409 Conflict** — the new name collides with another plan of the same
      product.
    """
    return plan_service.update_plan(session, plan_id=plan_id, payload=payload)


@router.delete(
    "/plans/{plan_id}",
    status_code=204,
    summary="Delete a plan (admin only)",
    response_description="The plan was deleted; no content is returned.",
    responses={
        204: {"description": "The plan was deleted."},
        403: {"description": "The caller lacks administrator privileges."},
        404: {"description": "No plan exists with this id."},
    },
)
def delete_plan(
    plan_id: int = Path(..., description="ID of the plan to delete."),
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    """Delete a plan.

    Once deleted, the plan no longer appears in the list/get endpoints (a
    subsequent ``GET /plans/{id}`` returns 404). Existing subscriptions to this
    plan's template versions are not affected.

    ## Authorization
    Requires administrator privileges. Other callers receive `403 Forbidden`.

    ## Parameters
    - **plan_id** (path) — the plan to delete.

    ## Behavior
    - Deleting a plan that does not exist returns 404.
    - On success the endpoint returns ``204 No Content``.

    ## Errors
    - **404 Not Found** — no plan exists with this id.
    - **403 Forbidden** — the caller is not an administrator.
    """
    plan_service.delete_plan(session, plan_id=plan_id)


# ---------------------------------------------------------------------------
# Plan template versions (admin only)
# ---------------------------------------------------------------------------


@router.get(
    "/plans/{plan_id}/templates",
    response_model=list[PlanTemplateVersionRead],
    summary="List a plan's template versions",
    response_description="All template versions for the plan.",
)
def list_plan_templates(
    plan_id: int = Path(..., description="ID of the plan whose template versions to list."),
    session: Session = Depends(get_session),
) -> list[PlanTemplateVersionRead]:
    """List the template versions of a plan.

    Template versions are immutable commercial-terms records (price, billing
    interval, storage and database quotas, description).

    ## Authorization
    Public — no authentication required.

    ## Parameters
    - **plan_id** (path) — the plan whose template versions are listed.

    ## Behavior
    - An unknown ``plan_id`` yields an empty array rather than a 404.

    ## Errors
    - A malformed ``plan_id`` (non-integer) is rejected with 422.
    """
    return plan_service.list_plan_template_versions(session, plan_id)


@router.post(
    "/plans/{plan_id}/templates",
    response_model=PlanTemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a plan template version (admin only)",
    response_description="The newly created template version.",
    responses={
        201: {"description": "The template version was created."},
        403: {"description": "The caller lacks administrator privileges."},
        404: {"description": "No plan exists with this id."},
        422: {
            "description": (
                "Request body validation failed (e.g. missing `price_cents`/"
                "`billing_interval`, or an invalid `billing_interval` value)."
            )
        },
    },
)
def create_plan_template(
    plan_id: int = Path(
        ..., description="ID of the plan the template version belongs to (taken from the path)."
    ),
    payload: PlanTemplateVersionCreate = ...,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanTemplateVersionRead:
    """Create a new template version (commercial terms) for a plan.

    Template versions are immutable: to change pricing you create a new version
    and then select it as the plan's current terms via ``PUT /plans/{plan_id}``.
    Creating a version does NOT automatically make it the plan's current terms.

    ## Authorization
    Requires administrator privileges. Other callers receive `403 Forbidden`.

    ## Parameters
    - **plan_id** (path) — the owning plan. This value is authoritative: the
      version's ``plan_id`` is always taken from the path, not the body.
    - **price_cents** (body, required) — price in cents. ``0`` denotes a free
      plan.
    - **billing_interval** (body, required) — exactly ``monthly`` or ``annual``;
      any other value is a 422. A product offering both is modeled as two plans.
    - **storage_bytes** (body, optional) — object storage quota in bytes; when
      omitted, the deployment uses its default storage size.
    - **database_bytes** (body, optional) — relational database quota in bytes.
      A separate allowance from ``storage_bytes``, bounding a separate
      subsystem; when omitted, the plan grants no relational storage.
    - **description** (body, optional) — Markdown summary of the terms.

    ## Behavior
    - The plan must exist; otherwise 404.
    - The created version is returned with 201; it does not become the plan's
      current terms here.

    ## Errors
    - **404 Not Found** — the plan does not exist.
    - **403 Forbidden** — the caller is not an administrator.
    - **422 Unprocessable Entity** — body validation failed (missing required
      fields or an invalid ``billing_interval``).
    """
    return plan_service.create_plan_template_version(
        session, plan_id=plan_id, payload=payload
    )
