"""The release history: what this project's deployment has rolled out.

Unlike the build history, this one is inherently project-scoped — a release
belongs to a deployment, and the platform has no account-wide release listing
to fall back on. So the command needs a project that records a deployment, and
says so plainly when there is none.

The running release is marked from what the deployment reports as *applied*,
never from the top of the listing: after a failed rollout the newest release is
not the one serving traffic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from . import FreepodError
from .api import ApiClient
from .table import BLANK, abbreviate, elapsed, format_duration, format_time, render

#: How many releases a bare `freepod releases` shows. The endpoint has no
#: pagination and returns the lot, so this is a display bound, not a query one.
DEFAULT_LIMIT = 20

#: Marks the release the deployment is currently running.
LIVE_MARKER = "*"

COLUMNS = ("", "RELEASE", "STATUS", "CREATED", "DURATION", "IMAGE")


def list_releases(api: ApiClient, user_id: int, deployment_id: str) -> List[Dict[str, Any]]:
    """The deployment's releases, most recent first.

    The order is the platform's, and is kept: it orders by release number,
    which is the ledger's own ordering key.
    """
    path = f"/api/users/{user_id}/deployments/{deployment_id}/releases"
    body = api.get_json(path)
    if not isinstance(body, list):
        raise FreepodError(f"unexpected {path} response: {body!r}")
    return [entry for entry in body if isinstance(entry, dict)]


def read_deployment(
    api: ApiClient, user_id: int, deployment_id: str
) -> Optional[Dict[str, Any]]:
    """The deployment, or None where the platform no longer has it.

    Read only for the mark, so a miss costs the mark and not the listing.
    """
    response = api.get(f"/api/users/{user_id}/deployments/{deployment_id}")
    if not response.is_success:
        return None
    body = response.json()
    return body if isinstance(body, dict) else None


def applied_number(deployment: Any) -> Optional[int]:
    """The number of the release the deployment is running, if it reports one.

    Reads `applied_release` and never `desired_release`: the desired one is
    what was asked for, which after a failed rollout is not what is running.
    Every way of not knowing answers None — the mark is a convenience, and the
    listing is the result.
    """
    if not isinstance(deployment, dict):
        return None
    applied = deployment.get("applied_release")
    if not isinstance(applied, dict):
        return None
    number = applied.get("number")
    return number if isinstance(number, int) else None


def image_of(release: Dict[str, Any]) -> Optional[str]:
    """The image the release shipped, from the build inlined on it."""
    build = release.get("build")
    if not isinstance(build, dict):
        return None
    image = build.get("image")
    return image if isinstance(image, str) and image else None


def failures(releases: Sequence[Dict[str, Any]]) -> List[str]:
    """`(number, error)` lines for the releases that recorded one."""
    notes = []
    for release in releases:
        error = release.get("error")
        if isinstance(error, str) and error.strip():
            notes.append(f"release {release.get('number', BLANK)} failed: {error.strip()}")
    return notes


def rows(
    releases: Sequence[Dict[str, Any]],
    *,
    live_number: Optional[int] = None,
    full_image: bool = False,
    now: Optional[datetime] = None,
) -> List[List[str]]:
    """One row per release, in the order given, headers first."""
    table = [list(COLUMNS)]
    for release in releases:
        number = release.get("number")
        live = live_number is not None and number == live_number
        table.append(
            [
                LIVE_MARKER if live else "",
                str(number if number is not None else BLANK),
                str(release.get("status", BLANK)),
                format_time(release.get("created_at")),
                format_duration(
                    elapsed(release.get("started_at"), release.get("ended_at"), now)
                ),
                abbreviate(image_of(release), full=full_image),
            ]
        )
    return table


def render_table(
    releases: Sequence[Dict[str, Any]],
    *,
    live_number: Optional[int] = None,
    full_image: bool = False,
    now: Optional[datetime] = None,
) -> str:
    """The rendered table, ready for stdout."""
    return render(
        rows(releases, live_number=live_number, full_image=full_image, now=now)
    )
