"""`freepod var`: a deployment's runtime configuration.

Values are strings on the wire. A sensitive var is write-only — the platform
returns it with no `value` at all — so an entry carrying no value means "leave
this one alone", which is what makes `var list --json` output safe to submit
back through `var set -f -`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from . import FreepodError, UsageError
from .api import ApiClient
from .table import GAP

#: The only phase that currently exists. Leaves room for build vars.
PHASE = "runtime"

#: Stands in for a value the platform will not return.
HIDDEN = "<hidden>"

COLUMNS = ("KEY", "VALUE")


def _base(user_id: int, deployment_id: str) -> str:
    return f"/api/users/{user_id}/deployments/{deployment_id}/vars/{PHASE}"


def read(api: ApiClient, user_id: int, deployment_id: str) -> Dict[str, Any]:
    """The deployment's vars envelope: `{"vars": {...}, "pending": bool}`."""
    body = api.get_json(_base(user_id, deployment_id))
    if not isinstance(body, dict):
        raise FreepodError(f"unexpected vars response: {body!r}")
    return body


def write(
    api: ApiClient, user_id: int, deployment_id: str, entries: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge `entries` into the deployment's vars."""
    response = api.request(
        "PATCH", _base(user_id, deployment_id), json={"vars": entries}
    )
    if not response.is_success:
        raise _write_error(response)
    return response.json()


def remove(api: ApiClient, user_id: int, deployment_id: str, keys: List[str]) -> None:
    """Delete keys. Removing one that is not set is a no-op, not an error."""
    for key in keys:
        response = api.delete(f"{_base(user_id, deployment_id)}/{key}")
        if not response.is_success:
            raise _write_error(response)


def _write_error(response) -> FreepodError:
    detail = ""
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else ""
    except ValueError:
        detail = response.text.strip()[:300]
    return FreepodError(detail or f"the platform refused the write: HTTP {response.status_code}")


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


def parse_assignments(
    arguments: List[str], *, interactive: bool, prompt=click.prompt
) -> Dict[str, str]:
    """`KEY=VALUE` pairs; a bare `KEY` is prompted for without echo.

    Prompting is what keeps a secret out of the shell history, so a bare key
    with nowhere to prompt is a usage error rather than an empty value.
    """
    values: Dict[str, str] = {}
    for argument in arguments:
        key, separator, value = argument.partition("=")
        key = key.strip()
        if not key:
            raise UsageError(f"'{argument}' is not a KEY=VALUE pair")
        if separator:
            values[key] = value
            continue
        if not interactive:
            raise UsageError(
                f"no value given for {key}, and there is no terminal to prompt on.\n"
                f"  Pass {key}=VALUE, or -f FILE, or pipe the wire shape into -f -."
            )
        values[key] = prompt(f"Value for {key}", hide_input=True)
    return values


def load_entries(source: str) -> Dict[str, Any]:
    """Read vars from a file, or from stdin when `source` is `-`.

    Accepts the platform's own wire shape (so `var list --json` round-trips)
    or plain `KEY=VALUE` lines.
    """
    if source == "-":
        text = sys.stdin.read()
        origin = "standard input"
    else:
        path = Path(source)
        if not path.is_file():
            raise UsageError(f"{source}: no such file")
        text = path.read_text(encoding="utf-8")
        origin = source

    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UsageError(f"{origin}: not valid JSON ({exc})") from exc
        return _entries_from_wire(document, origin)
    return {key: {"value": value} for key, value in _entries_from_lines(text, origin).items()}


def _entries_from_wire(document: Any, origin: str) -> Dict[str, Any]:
    if not isinstance(document, dict):
        raise UsageError(f"{origin}: expected an object")
    # Both the envelope and a bare map, because one is what `--json` prints and
    # the other is what a person writing the file by hand would produce.
    vars_ = document.get("vars", document)
    if not isinstance(vars_, dict):
        raise UsageError(f"{origin}: 'vars' is not an object")

    entries: Dict[str, Any] = {}
    for key, entry in vars_.items():
        if isinstance(entry, str) or entry is None:
            entries[key] = {"value": entry}
            continue
        if not isinstance(entry, dict):
            raise UsageError(f"{origin}: {key} is neither a string nor an object")
        # Only the two fields a write carries. `updated_at`/`updated_by` come
        # back on a read and are the platform's to set.
        kept: Dict[str, Any] = {}
        if "value" in entry:
            kept["value"] = entry["value"]
        if "sensitive" in entry:
            kept["sensitive"] = entry["sensitive"]
        entries[key] = kept
    return entries


def _entries_from_lines(text: str, origin: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not key.strip():
            raise UsageError(f"{origin}:{number}: expected KEY=VALUE, got {line!r}")
        values[key.strip()] = value
    return values


def schema_declares(deployment: Dict[str, Any], key: str) -> bool:
    """Whether the deployment's template declares `key`, and so owns its
    sensitivity."""
    template = deployment.get("desired_template") or {}
    schema = template.get("values_schema_json") or {}
    properties = schema.get("properties") if isinstance(schema, dict) else None
    return isinstance(properties, dict) and key in properties


def mark_sensitive(
    entries: Dict[str, Any], deployment: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """Flag every entry sensitive, except where the schema already decides.

    Returns the entries and the keys left alone, which the caller warns about.
    """
    marked: Dict[str, Any] = {}
    declared: List[str] = []
    for key, entry in entries.items():
        if schema_declares(deployment, key):
            declared.append(key)
            marked[key] = entry
            continue
        marked[key] = {**entry, "sensitive": True}
    return marked, declared


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def rows(payload: Dict[str, Any]) -> List[Tuple[str, str]]:
    entries = payload.get("vars") or {}
    return [
        (key, HIDDEN if "value" not in entry else str(entry.get("value", "")))
        for key, entry in sorted(entries.items())
    ]


def render_table(payload: Dict[str, Any]) -> str:
    body = rows(payload)
    if not body:
        return ""
    widths = [max(len(str(cell)) for cell in column) for column in zip(COLUMNS, *body)]
    lines = [GAP.join(head.ljust(width) for head, width in zip(COLUMNS, widths)).rstrip()]
    lines += [
        GAP.join(str(cell).ljust(width) for cell, width in zip(row, widths)).rstrip()
        for row in body
    ]
    return "\n".join(lines)


def pending_count(
    api: ApiClient, user_id: int, deployment: Dict[str, Any]
) -> Optional[int]:
    """How many vars a rollout would change, or None if it cannot be told.

    Needs the applied release's snapshot, which the deployment read does not
    inline; fetched only when the deployment reports something pending.
    """
    if not deployment.get("pending"):
        return 0
    head = deployment.get("vars") or {}
    applied = deployment.get("applied_release") or {}
    number = applied.get("number")
    if number is None:
        return len(head)
    path = (
        f"/api/users/{user_id}/deployments/{deployment['id']}/releases/{number}"
    )
    response = api.get(path)
    if not response.is_success:
        return None
    running = (response.json() or {}).get("vars") or {}
    changed = {
        key for key in set(head) | set(running) if _entry(head, key) != _entry(running, key)
    }
    return len(changed)


def _entry(entries: Dict[str, Any], key: str) -> Any:
    entry = entries.get(key)
    if not isinstance(entry, dict):
        return None
    # A sensitive var carries no value either side, so it compares by its
    # timestamp: that is what changes when it is rewritten.
    return entry.get("value"), entry.get("sensitive"), entry.get("updated_at")
