"""The build history: reading an account's builds and rendering them.

A build is owned by a **user**, never by a deployment or a project — the
platform has no notion of a project at all, and the account's build listing
answers with
everything the caller has ever built. So this lists the account's builds and
annotates the one whose image the current project is actually running, which is
the closest thing to a project-scoped history the platform can answer.

That annotation is why the deployment is read at all: without it the listing
cannot distinguish the build that is serving traffic from the four newer ones
that were built and never released.

The table is the command's **result** and goes to stdout; the legend and the
counts are diagnostics and go to stderr, so `freepod builds | ...` carries rows
and nothing else.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import FreepodError
from .api import ApiClient
from .project import find_project_root, load
from .table import (  # noqa: F401  (re-exported for callers of this module)
    BLANK,
    GAP,
    SHORT_DIGEST,
    abbreviate,
    elapsed,
    format_duration,
    format_time,
    parse_time,
    render,
)

#: How many builds a bare `freepod builds` shows. The endpoint has no
#: pagination and returns the lot, so this is a display bound, not a query one.
DEFAULT_LIMIT = 20

#: Marks the build whose image the project's deployment is currently running.
LIVE_MARKER = "*"

COLUMNS = ("", "BUILD", "STATUS", "CREATED", "DURATION", "IMAGE")


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def list_builds(api: ApiClient, user_id: int) -> List[Dict[str, Any]]:
    """`GET /api/users/{user_id}/builds` — the account's builds, most recent first.

    The order is the platform's, and is kept: re-sorting here would mean
    parsing every timestamp just to reproduce the answer already given, and
    would silently reorder rows the moment a timestamp failed to parse.
    """
    path = f"/api/users/{user_id}/builds"
    body = api.get_json(path)
    if not isinstance(body, list):
        raise FreepodError(f"unexpected {path} response: {body!r}")
    return [entry for entry in body if isinstance(entry, dict)]


def deployed_image(
    api: ApiClient, user_id: int, env_name: str, root: Optional[Path] = None
) -> Optional[str]:
    """The image this project's deployment runs, if there is one to read.

    Every way of not knowing answers None: no project file, one belonging to a
    different environment, no deployment recorded yet, or a deployment the
    platform no longer has. None of them is a reason to refuse a listing that
    would otherwise be perfectly good — the annotation is a convenience, and
    the listing is the result.
    """
    found = find_project_root(root)
    if found is None:
        return None

    project = load(found)
    if project.env != env_name or not project.deployment_id:
        return None

    response = api.get(f"/api/users/{user_id}/deployments/{project.deployment_id}")
    if not response.is_success:
        return None

    values = response.json().get("user_values_json")
    image = values.get("image") if isinstance(values, dict) else None
    return image if isinstance(image, str) and image else None


def duration(build: Dict[str, Any], now: Optional[datetime] = None) -> Optional[timedelta]:
    """How long the build ran, or has been running."""
    return elapsed(build.get("started_at"), build.get("finished_at"), now)


def rows(
    builds: Sequence[Dict[str, Any]],
    *,
    live_image: Optional[str] = None,
    full_image: bool = False,
    now: Optional[datetime] = None,
) -> List[List[str]]:
    """One row per build, in the order given, headers first."""
    table = [list(COLUMNS)]
    for build in builds:
        image = build.get("image")
        live = bool(live_image) and image == live_image
        table.append(
            [
                LIVE_MARKER if live else "",
                str(build.get("id", BLANK)),
                str(build.get("status", BLANK)),
                format_time(build.get("created_at")),
                format_duration(duration(build, now)),
                abbreviate(image, full=full_image),
            ]
        )
    return table
