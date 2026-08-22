from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, Path, Response, status
from fastapi.responses import PlainTextResponse
from sqlmodel import Session
from uuid import UUID

from app.db import get_session
from app.deps import require_self
from app.models import BuildCreate, BuildRead, UserORM
from app.services import builds as build_service

router = APIRouter(prefix="/users/{user_id}/builds", tags=["builds"])

# Only the two forms a polling client produces: `bytes=N-` and `bytes=N-M`.
# Anything else — a suffix range, multiple ranges, a unit other than bytes — is
# ignored and answered in full, which RFC 7233 explicitly permits and which
# keeps the parser small enough to be obviously correct.
_RANGE_RE = re.compile(r"^bytes=(\d+)-(\d*)$")


def _parse_range(value: str | None) -> tuple[int, int | None] | None:
    """`(start, end)` for a supported byte range, else None to serve in full."""
    if not value:
        return None
    match = _RANGE_RE.match(value.strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else None
    if end is not None and end < start:
        return None
    return start, end


@router.post(
    "",
    response_model=BuildRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a build from an uploaded artifact",
    response_description=(
        "The build, in `queued` status, owned by the authenticated caller. "
        "`Location` carries its URL."
    ),
    responses={
        201: {"description": "A new build was queued."},
        200: {
            "description": (
                "A build for this artifact was already in flight and is "
                "returned unchanged; no second build was created."
            )
        },
        400: {"description": "The artifact id is malformed, or no such artifact was uploaded."},
        403: {"description": "Caller may only create builds under their own account."},
        404: {"description": "The request carried no authenticated identity."},
        422: {"description": "The body carried a field other than `artifact_id` (such as `user_id`)."},
    },
)
def create_build(
    payload: BuildCreate,
    response: Response,
    user_id: int = Path(..., description="ID of the user the build is created for."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> BuildRead:
    """Queue a build of an artifact previously uploaded via `POST /api/artifacts`.

    Phase three of three. The body carries **only** `artifact_id`; the owner
    comes from the authenticated session, and any other field — `user_id`
    included — is rejected outright rather than quietly dropped. The path
    `user_id` says whose account is being acted on and is what authorizes the
    request; it is not where the owner comes from.

    ## Behavior
    Retrying while the original build is still `queued` or `running` returns
    that build with **200** instead of creating a second one. Once every build
    for the artifact is terminal, a repeat request creates a new build, so a
    transient failure can be rebuilt without re-uploading the archive.

    Nothing here triggers a rollout: on success the client submits the build's
    `image` to the deployment update endpoint itself.
    """
    result = build_service.create_build(session, user_id=current_user.id, payload=payload)
    response.headers["Location"] = f"/api/users/{user_id}/builds/{result.build.id}"
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return result.build


@router.get(
    "",
    response_model=list[BuildRead],
    summary="List a user's builds",
    response_description="A JSON array of the user's builds, most recent first.",
    responses={
        200: {"description": "The user's builds, most recent first."},
        403: {"description": "A non-administrator asked for another user's builds."},
        404: {"description": "The request carried no authenticated identity."},
    },
)
def list_builds(
    user_id: int = Path(..., description="ID of the user whose builds to list."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> list[BuildRead]:
    """Return the builds owned by `user_id`, most recent first.

    ## Authorization
    You may only list your own builds; administrators may list any account's.
    Other requests receive **403 Forbidden**.

    ## Behavior
    Enumeration is what keeps a previously produced image reachable after a
    client has forgotten its build id, which is what a redeploy or a rollback
    needs.
    """
    return build_service.list_builds(
        session, user_id=None if current_user.is_admin else user_id
    )


@router.get(
    "/{build_id}",
    response_model=BuildRead,
    summary="Read a build",
    response_description=(
        "The build's status, timestamps, artifact id, and `image` — the last "
        "being null until the build succeeds."
    ),
    responses={
        200: {"description": "The build."},
        403: {"description": "Caller may only read their own builds."},
        404: {
            "description": (
                "No such build, or it belongs to another user — the two are "
                "deliberately indistinguishable."
            )
        },
    },
)
def get_build(
    user_id: int = Path(..., description="ID of the user that owns the build."),
    build_id: UUID = Path(..., description="ID of the build."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> BuildRead:
    """Return one of the user's builds.

    ## Authorization
    Scoped to your own builds; administrators may read any. Naming another
    account answers **403**; a build under your own account that belongs to
    someone else answers **404**, identically to one that does not exist, so
    the endpoint cannot be used to probe for other users' builds.
    """
    return build_service.get_build(
        session,
        build_id=build_id,
        user_id=None if current_user.is_admin else user_id,
    )


@router.get(
    "/{build_id}/log",
    response_class=PlainTextResponse,
    summary="Read a build's output, incrementally",
    response_description=(
        "The log as `text/plain`. Every response carries `X-Build-Status` with "
        "the build's current status."
    ),
    responses={
        200: {"description": "The full accumulated output."},
        206: {
            "description": (
                "The requested byte range. `Content-Range` reports the total "
                "length as unknown (`*`) because the log is still growing, and "
                "is omitted entirely when the range is empty — a range starting "
                "at the current end of the log returns an empty 206 rather than "
                "a 416, so a polling client needs no special case."
            )
        },
        403: {"description": "Caller may only read their own builds' logs."},
        404: {"description": "No such build, or it belongs to another user."},
    },
)
def get_build_log(
    user_id: int = Path(..., description="ID of the user that owns the build."),
    build_id: UUID = Path(..., description="ID of the build."),
    range_header: str | None = Header(
        None,
        alias="Range",
        description="Byte range to return, as `bytes=N-` or `bytes=N-M`.",
    ),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> Response:
    """Return a build's accumulated output as plain text.

    ## Polling
    Read without a `Range` to get everything, then poll with
    `Range: bytes=<bytes read so far>-` to get only what has been appended
    since. Stop when `X-Build-Status` reports a terminal status —
    `succeeded`, `failed`, or `canceled` — which saves a second request just
    to ask whether the build is done.

    Offsets are **bytes**, not characters. A chunk boundary can therefore fall
    inside a multi-byte character; concatenate the chunks and decode the
    result, rather than decoding each chunk on its own.

    ## Errors
    - **403 Forbidden** — reading another account's build log.
    - **404 Not Found** — no such build, or it belongs to another user.
    """
    parsed = _parse_range(range_header)
    slice_ = build_service.get_build_log(
        session,
        build_id=build_id,
        user_id=None if current_user.is_admin else user_id,
        start=parsed[0] if parsed else None,
        end=parsed[1] if parsed else None,
    )

    headers = {
        "X-Build-Status": slice_.status,
        "Accept-Ranges": "bytes",
        # The log is a moving target; a cached copy is a wrong copy.
        "Cache-Control": "no-store",
    }
    if not slice_.partial:
        return Response(content=slice_.data, media_type="text/plain; charset=utf-8", headers=headers)

    if slice_.data:
        last = slice_.start + len(slice_.data) - 1
        # `/*`: the build is still writing, so there is no total to assert.
        headers["Content-Range"] = f"bytes {slice_.start}-{last}/*"
    # An empty slice gets no Content-Range at all — the grammar has no way to
    # express a zero-length range, and inventing one would misreport a byte.
    return Response(
        content=slice_.data,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )
