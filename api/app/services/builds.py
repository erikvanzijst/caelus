"""Build lifecycle: creation, retrieval, listing, and log slicing.

Every read here takes a `user_id` scope exactly like `services/deployments.py`:
pass the caller's id to restrict results to their own builds, or ``None`` to
read across all users (which only an administrator's request should ever do).
A build owned by someone else raises ``NotFoundException`` rather than a
permission error, so it is indistinguishable from one that never existed.

Nothing in this module writes build *state* beyond creating the row. The
timestamps, `job_id`, `image`, and `log` all belong to the build worker — it is
the single writer for everything downstream of `queued`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import BuildCreate, BuildORM, BuildRead
from app.services.artifacts import artifact_exists, validate_artifact_id
from app.services.build_constants import BUILD_STATUSES_OPEN
from app.services.errors import IntegrityException, NotFoundException, ValidationException

logger = logging.getLogger(__name__)


@dataclass
class BuildCreateResult:
    """The build, and whether this request is what brought it into existence.

    `created` is false when an in-flight build for the same artifact was
    returned instead, which lets the endpoint answer 201 for a real creation
    and 200 for an idempotent retry.
    """

    build: BuildRead
    created: bool


@dataclass
class BuildLogSlice:
    """A window onto a build's output.

    `data` is raw bytes, straight out of the column. The log is stored as
    `bytea` precisely so that neither this nor the worker has to decode a
    tenant-controlled byte stream, and so that HTTP's byte offsets and the
    column's own length are the same number.

    `start` is the byte offset `data` begins at, after clamping — a client that
    polls from the current end of a growing log gets an empty `data` and a
    `start` at the end, not an error.
    """

    data: bytes
    start: int
    status: str
    partial: bool


def _get_build_orm(session: Session, *, build_id: UUID, user_id: int | None) -> BuildORM:
    build = session.get(BuildORM, build_id)
    if build is None or (user_id is not None and build.user_id != user_id):
        # Same answer for "does not exist" and "is not yours": a caller must
        # not be able to probe for the existence of other users' builds.
        raise NotFoundException("Build not found")
    return build


def _find_open_build(session: Session, *, user_id: int, artifact_id: str) -> BuildORM | None:
    """This user's non-terminal build for `artifact_id`, if any.

    Scoped by user on purpose. The database's partial unique index spans all
    users because artifact ids are server-generated and globally unique, but
    handing back a build the caller does not own would leak its existence.
    """
    return session.exec(
        select(BuildORM)
        .where(BuildORM.artifact_id == artifact_id)
        .where(BuildORM.user_id == user_id)
        .where(BuildORM.status.in_(BUILD_STATUSES_OPEN))  # type: ignore[attr-defined]
    ).first()


def create_build(session: Session, *, user_id: int, payload: BuildCreate) -> BuildCreateResult:
    """Queue a build of a previously uploaded artifact.

    The owner is the caller, always: `payload` carries only an artifact id and
    forbids extra fields, so there is no owner in the request to honor.

    Creation is idempotent over the window in which client retries actually
    happen. A retry arriving while the original build is still `queued` or
    `running` gets that build back; once every build for the artifact is
    terminal, a fresh one is created, because build failures are often
    transient and re-uploading an identical archive to retry would waste the
    upload for nothing.
    """
    artifact_id = validate_artifact_id(payload.artifact_id)

    existing = _find_open_build(session, user_id=user_id, artifact_id=artifact_id)
    if existing is not None:
        logger.info(
            "Build create is a retry; returning in-flight build id=%s user_id=%s",
            existing.id,
            user_id,
        )
        return BuildCreateResult(build=BuildRead.model_validate(existing), created=False)

    # Deliberately after the retry check: a build already in flight proves the
    # artifact was there when it started, and re-checking would both cost a
    # needless round trip and fail a legitimate retry whose artifact has since
    # been expired by the bucket's lifecycle rule.
    if not artifact_exists(user_id, artifact_id):
        raise ValidationException(
            f"Artifact {artifact_id} was not found; upload it before creating a build"
        )

    build = BuildORM(user_id=user_id, artifact_id=artifact_id)
    session.add(build)
    try:
        session.commit()
    except IntegrityError as exc:
        # Two creations raced. The partial unique index is the arbiter; the
        # loser adopts the winner's build rather than reporting a conflict.
        session.rollback()
        winner = _find_open_build(session, user_id=user_id, artifact_id=artifact_id)
        if winner is None:
            logger.warning("Build create conflicted for artifact_id=%s user_id=%s", artifact_id, user_id)
            raise IntegrityException("A build for this artifact is already in flight") from exc
        return BuildCreateResult(build=BuildRead.model_validate(winner), created=False)

    session.refresh(build)
    logger.info("Queued build id=%s user_id=%s artifact_id=%s", build.id, user_id, artifact_id)
    return BuildCreateResult(build=BuildRead.model_validate(build), created=True)


def get_build(session: Session, *, build_id: UUID, user_id: int | None = None) -> BuildRead:
    return BuildRead.model_validate(_get_build_orm(session, build_id=build_id, user_id=user_id))


def list_builds(session: Session, *, user_id: int | None = None) -> list[BuildRead]:
    """Builds, most recent first.

    Enumeration is what makes a previously produced image reachable again
    after a client has forgotten its build id — which is exactly what a
    redeploy or a rollback needs.
    """
    stmt = select(BuildORM).order_by(BuildORM.created_at.desc(), BuildORM.id.desc())  # type: ignore[attr-defined]
    if user_id is not None:
        stmt = stmt.where(BuildORM.user_id == user_id)
    return [BuildRead.model_validate(b) for b in session.exec(stmt).all()]


def get_build_log(
    session: Session,
    *,
    build_id: UUID,
    user_id: int | None = None,
    start: int | None = None,
    end: int | None = None,
) -> BuildLogSlice:
    """A build's output, optionally from `start` to `end` (inclusive, bytes).

    `start` past the current end of the log yields an empty slice rather than
    an error: the log grows while the build runs, so a client polling from the
    offset it last read to is in the *steady* state, not an exceptional one,
    and should not have to special-case it.
    """
    build = _get_build_orm(session, build_id=build_id, user_id=user_id)
    # `bytes(...)` normalizes whatever the driver hands back for a binary
    # column (psycopg gives bytes, some drivers a memoryview) so slicing and
    # `len` are uniform.
    data = bytes(build.log or b"")

    if start is None:
        return BuildLogSlice(data=data, start=0, status=build.status, partial=False)

    # Clamp rather than reject, so `start` is always a truthful offset for the
    # bytes actually returned.
    offset = min(max(start, 0), len(data))
    window = data[offset:] if end is None else data[offset : end + 1]
    return BuildLogSlice(data=window, start=offset, status=build.status, partial=True)
