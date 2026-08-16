"""The build history: reading an account's builds and rendering them.

A build is owned by a **user**, never by a deployment or a project — the
platform has no notion of a project at all, and `GET /api/builds` answers with
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

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import FreepodError
from .api import ApiClient
from .project import find_project_root, load

#: How many builds a bare `freepod builds` shows. The endpoint has no
#: pagination and returns the lot, so this is a display bound, not a query one.
DEFAULT_LIMIT = 20

#: Digest characters kept when abbreviating an image reference. Twelve is the
#: conventional short form and is what makes a column of them comparable at a
#: glance; `--verbose` prints the reference in full.
SHORT_DIGEST = 12

#: Marks the build whose image the project's deployment is currently running.
LIVE_MARKER = "*"

COLUMNS = ("", "BUILD", "STATUS", "CREATED", "DURATION", "IMAGE")

#: Column separator. Two spaces, so a value can never be mistaken for a
#: boundary and `awk` still splits the rows.
GAP = "  "

#: Shown where the platform has no value yet — a queued build has no duration,
#: a failed one has no image.
BLANK = "-"


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def list_builds(api: ApiClient) -> List[Dict[str, Any]]:
    """`GET /api/builds` — the caller's builds, most recent first.

    The order is the platform's, and is kept: re-sorting here would mean
    parsing every timestamp just to reproduce the answer already given, and
    would silently reorder rows the moment a timestamp failed to parse.
    """
    body = api.get_json("/api/builds")
    if not isinstance(body, list):
        raise FreepodError(f"unexpected /api/builds response: {body!r}")
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


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def parse_time(value: Any) -> Optional[datetime]:
    """One of the platform's timestamps, as an aware UTC datetime.

    The API serializes naive datetimes that are UTC by construction, so a
    missing offset is read as UTC rather than as local time — reading it as
    local would misreport every duration by the reader's own offset.
    """
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp


def format_time(value: Any) -> str:
    """A timestamp in the reader's own timezone, to the minute.

    Local, because the question a history answers is "was that before or after
    the thing I remember doing", and the reader remembers it in local time.
    """
    stamp = parse_time(value)
    if stamp is None:
        return str(value) if value else BLANK
    return stamp.astimezone().strftime("%Y-%m-%d %H:%M")


def format_duration(delta: Optional[timedelta]) -> str:
    """`45s`, `3m 12s`, `1h 4m` — two units at most, largest first."""
    if delta is None:
        return BLANK
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return BLANK
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def duration(build: Dict[str, Any], now: Optional[datetime] = None) -> Optional[timedelta]:
    """How long the build ran, or has been running.

    Measured from `started_at`, not `created_at`: the wait for a worker is
    queueing, and counting it would report a five-second build as a five-minute
    one whenever the queue was busy.
    """
    started = parse_time(build.get("started_at"))
    if started is None:
        return None
    finished = parse_time(build.get("finished_at"))
    if finished is None:
        return (now or datetime.now(timezone.utc)) - started
    return finished - started


def abbreviate(image: Any, *, full: bool = False) -> str:
    """Shorten a digest reference to its first twelve characters.

    A full reference is 75 characters of which 64 are a digest, which would
    make the column wider than every other one put together. Truncation is
    marked, never silent.
    """
    if not isinstance(image, str) or not image:
        return BLANK
    if full:
        return image
    head, marker, digest = image.rpartition("sha256:")
    if marker and len(digest) > SHORT_DIGEST:
        return f"{head}{marker}{digest[:SHORT_DIGEST]}…"
    return image


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


def render(table: Sequence[Sequence[str]]) -> str:
    """Left-aligned columns, sized to their contents, with no trailing space."""
    widths = [max(len(row[column]) for row in table) for column in range(len(COLUMNS))]
    lines = [
        GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in table
    ]
    return "\n".join(lines)
