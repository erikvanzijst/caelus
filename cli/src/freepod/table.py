"""Shared rendering for the client's listing commands.

A leaf module: `builds` and `releases` both draw the same kind of table, and
neither should have to import the other to do it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence

#: Digest characters kept when abbreviating an image reference. Twelve is the
#: conventional short form and is what makes a column of them comparable at a
#: glance; `--verbose` prints the reference in full.
SHORT_DIGEST = 12

#: Column separator. Two spaces, so a value can never be mistaken for a
#: boundary and `awk` still splits the rows.
GAP = "  "

#: Shown where the platform has no value yet — a queued build has no duration,
#: a failed one has no image.
BLANK = "-"


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
    """A timestamp in the reader's own timezone, to the minute."""
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


def elapsed(
    started: Any, finished: Any, now: Optional[datetime] = None
) -> Optional[timedelta]:
    """How long the work ran, or has been running.

    Measured from when work *started*, never from when the record was created:
    the wait for a worker is queueing, and counting it would report a
    five-second job as a five-minute one whenever the queue was busy.
    """
    begin = parse_time(started)
    if begin is None:
        return None
    end = parse_time(finished)
    if end is None:
        return (now or datetime.now(timezone.utc)) - begin
    return end - begin


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


def render(table: Sequence[Sequence[str]]) -> str:
    """Left-aligned columns, sized to their contents, with no trailing space."""
    if not table:
        return ""
    columns = len(table[0])
    widths = [max(len(row[column]) for row in table) for column in range(columns)]
    lines: List[str] = [
        GAP.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in table
    ]
    return "\n".join(lines)
