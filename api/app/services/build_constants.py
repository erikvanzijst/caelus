from __future__ import annotations

BUILD_STATUS_QUEUED = "queued"
BUILD_STATUS_RUNNING = "running"
BUILD_STATUS_SUCCEEDED = "succeeded"
BUILD_STATUS_FAILED = "failed"
# Reserved. Nothing transitions a build into it today; it exists so that adding
# cancellation later does not have to widen the status column's vocabulary and
# re-audit every consumer that switches on it.
BUILD_STATUS_CANCELED = "canceled"

BUILD_STATUSES: tuple[str, ...] = (
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCEEDED,
    BUILD_STATUS_FAILED,
    BUILD_STATUS_CANCELED,
)

# Statuses a build can still move out of. The partial unique index on
# `build.artifact_id` is scoped to exactly these, so the tuple's membership is
# also a schema fact: changing it requires a migration, not just a code change.
BUILD_STATUSES_OPEN: tuple[str, ...] = (
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
)

BUILD_STATUSES_TERMINAL: tuple[str, ...] = (
    BUILD_STATUS_SUCCEEDED,
    BUILD_STATUS_FAILED,
    BUILD_STATUS_CANCELED,
)

# The whole state machine. A failed build is terminal and is never retried
# automatically — recovery is creating a new build — so no edge leaves a
# terminal status, and there is deliberately no edge back into `queued`.
BUILD_TRANSITIONS: dict[str, tuple[str, ...]] = {
    BUILD_STATUS_QUEUED: (BUILD_STATUS_RUNNING,),
    BUILD_STATUS_RUNNING: (BUILD_STATUS_SUCCEEDED, BUILD_STATUS_FAILED),
    BUILD_STATUS_SUCCEEDED: (),
    BUILD_STATUS_FAILED: (),
    BUILD_STATUS_CANCELED: (),
}


def is_terminal(status: str) -> bool:
    """Whether `status` is one no further transition leaves."""
    return status in BUILD_STATUSES_TERMINAL


def can_transition(current: str, new: str) -> bool:
    """Whether `current -> new` is a permitted build state transition."""
    return new in BUILD_TRANSITIONS.get(current, ())
