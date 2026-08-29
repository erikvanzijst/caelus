"""`freepod db`: the deployment's PostgreSQL database.

**No address, and no connection URL.** The platform reports the pooler's host
and port, and both resolve inside the cluster and nowhere else — so a URL built
around them would look exactly like the input to `psql` and connect from
nowhere the reader is standing. The URL that will connect is the one the
forwarding client composes around its own local address, which is also why it
cannot use a server-composed one. What this module reports is the part that
stays true on both sides of that tunnel: which database and role the deployment
owns, the password that owns them, and how much of the allowance is used.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import FreepodError
from .api import ApiClient
from .table import format_time, render

NO_DATABASE_CODE = "relational_storage_unavailable"

#: Fixed width, so the mask does not report the password's length.
MASK = "•" * 12

REVEAL_HINT = "(--show-password to reveal)"

#: What each quota state means to the person who owns the data. A state name on
#: its own answers nothing: someone runs this command *because* writes started
#: failing.
STATE_CONSEQUENCE = {
    "ok": "healthy",
    "warned": "approaching its allowance",
    "readonly": "read-only — over its allowance, so every write is rejected",
    "blocked": "suspended — far over its allowance, so your app cannot connect",
}


def _path(user_id: int, deployment_id: str) -> str:
    return f"/api/users/{user_id}/deployments/{deployment_id}/database"


def read(api: ApiClient, user_id: int, deployment_id: str) -> Optional[Dict[str, Any]]:
    """The deployment's database details, or None when it has none.

    None is an answer rather than a failure: a product that offers no
    relational storage is a normal state, and so is the interval before a new
    deployment's first reconcile has provisioned one. Both carry the platform's
    stable code; a 404 without it is a missing deployment and stays an error.
    """
    response = api.get(_path(user_id, deployment_id))
    if response.status_code == 404:
        try:
            body = response.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and body.get("code") == NO_DATABASE_CODE:
            return None
        detail = body.get("detail") if isinstance(body, dict) else None
        raise FreepodError(detail or "no such deployment")

    if not response.is_success:
        raise FreepodError(
            f"HTTP {response.status_code} from {response.url}: "
            f"{response.text.strip()[:300]}"
        )
    body = response.json()
    if not isinstance(body, dict):
        raise FreepodError(f"unexpected database response: {body!r}")
    return body


def format_bytes(count: int) -> str:
    if count >= 1024 ** 4:
        return f"{count / 1024 ** 4:.1f} TB"
    if count >= 1024 ** 3:
        return f"{count / 1024 ** 3:.1f} GB"
    if count >= 1024 ** 2:
        return f"{count / 1024 ** 2:.0f} MB"
    if count >= 1024:
        return f"{count / 1024:.0f} KB"
    return f"{count} B"


def render_status(details: Dict[str, Any], *, show_password: bool) -> str:
    """The command's result: identity, credential and health, as a table."""
    password = details.get("password")
    if password is None:
        # Withheld from anyone but the owner, and said so: a client that cannot
        # tell "withheld" from "absent" has to guess.
        shown = "withheld — only the owner can read it"
    elif show_password:
        shown = password
    else:
        shown = f"{MASK} {REVEAL_HINT}"

    rows = [
        ("Database", str(details.get("database", ""))),
        ("Role", str(details.get("role", ""))),
        ("Password", shown),
        ("Usage", _usage(details)),
        ("State", STATE_CONSEQUENCE.get(details.get("quota_state"), str(details.get("quota_state")))),
    ]
    return render(rows)


def format_usage(size: int, allowance: int) -> str:
    """How full the database is, as a percentage with the figures behind it."""
    figures = f"{format_bytes(size)} of {format_bytes(allowance)}"
    if allowance <= 0:
        return figures
    percent = size / allowance * 100
    shown = "<1" if 0 < percent < 1 else str(round(percent))
    return f"{shown}% ({figures})"


def _usage(details: Dict[str, Any]) -> str:
    """Usage against the allowance, with the age of the figure."""
    allowance = details.get("allowance_bytes")
    allowance_text = format_bytes(allowance) if isinstance(allowance, int) else "unknown"

    size = details.get("size_bytes")
    if size is None:
        return f"not yet measured (allowance {allowance_text})"
    if not isinstance(allowance, int):
        return f"{format_bytes(size)} (allowance {allowance_text})"
    return (
        f"{format_usage(size, allowance)}"
        f" — measured {format_time(details.get('measured_at'))}"
    )
