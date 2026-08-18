"""Thin transport over Loki's query API.

Deliberately free of deployment and release concepts, following
``garage.py``: this module knows about LogQL selectors, nanosecond
timestamps and stream labels, and nothing about whose logs they are. Building
a selector from an authorized deployment row, resuming, keepalives and stream
limits all live in the endpoint.

**Polling `/query_range`, not the `/tail` WebSocket.** Recorded here because it
is the kind of decision that gets revisited:

* ``httpx`` -- the only HTTP client ``api/`` has -- has no WebSocket support,
  so ``/tail`` would mean a new dependency for one endpoint.
* ``/tail`` has documented boundary-loss caveats around the moment it starts.
* Polling reuses one code path for the bounded read, the first connect and
  every resume, so the three cannot drift apart.

The client contract is identical either way: nothing a caller sees depends on
which is used, so this can be revisited without touching the endpoint or the
CLI.

**Two shapes worth knowing before touching this:**

* **Timestamps are strings and must stay strings.** Loki returns nanosecond
  timestamps as decimal strings because the values (~1.76e18) exceed what an
  IEEE-754 double represents exactly. They are parsed to ``int`` where
  arithmetic is genuinely needed and never to ``float``.

* **`start` is inclusive and `end` is exclusive.** That asymmetry is what makes
  an inclusive resume expressible at all: handing back the last timestamp seen
  re-delivers the lines sharing that instant rather than skipping them.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Mapping

import httpx

from app.config import CaelusSettings, get_settings
from app.services.errors import CaelusException

logger = logging.getLogger(__name__)

QUERY_RANGE_PATH = "/loki/api/v1/query_range"

# Loki returns newest-first for `backward` and oldest-first for `forward`, and
# defaults to `backward`. Both are used here -- the first connect wants the
# newest N, every resume wants everything after a point -- so the default is
# never relied on; `direction` is always passed explicitly.
DIRECTION_FORWARD = "forward"
DIRECTION_BACKWARD = "backward"


class LokiException(CaelusException):
    """A Loki query failed, or the log store is not configured.

    Distinct from an empty result on purpose, and the distinction is the whole
    point: an unreachable store must never be reported as an application that
    printed nothing.
    """


@dataclass(frozen=True)
class LogEntry:
    """One log line as the store holds it."""

    # Nanoseconds since the epoch, as a decimal string. A string end to end:
    # see the module docstring.
    timestamp_ns: str
    line: str
    # The stream labels the line arrived with -- `namespace`, `instance`,
    # `release_id` where the pods are labelled. Passed through verbatim; giving
    # them meaning is the caller's job.
    labels: Mapping[str, str]


class LokiQueryClient:
    """Client for Loki's query API.

    Sync and async variants of the one call, because both are needed: the log
    endpoint is `async def` (a blocking stream would hold one of the API's 40
    worker threads for the life of the connection), while the reconciler
    fetches a failed release's tail from ordinary synchronous code.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._async_client = async_client

    @classmethod
    def from_settings(cls, settings: CaelusSettings | None = None, **kwargs: Any) -> LokiQueryClient:
        """Build a client, failing here rather than at import if unconfigured.

        `loki_base_url` defaults to empty so that migrations, the test suite and
        the operator CLI all construct settings happily; only a caller that
        actually wants logs pays for the store not being set up.
        """
        settings = settings or get_settings()
        if not settings.loki_base_url:
            raise LokiException("Log store is not configured: loki_base_url is unset")
        return cls(
            base_url=settings.loki_base_url,
            timeout_seconds=settings.loki_query_timeout_seconds,
            **kwargs,
        )

    # --- request construction ---------------------------------------------

    def _params(
        self,
        *,
        query: str,
        start_ns: int,
        end_ns: int | None,
        limit: int,
        direction: str,
    ) -> dict[str, str]:
        params = {
            "query": query,
            # Decimal strings, not ints: httpx would render them the same way,
            # but keeping the nanosecond values out of any numeric round trip
            # is a rule worth applying uniformly rather than case by case.
            "start": str(start_ns),
            "limit": str(limit),
            "direction": direction,
        }
        if end_ns is not None:
            params["end"] = str(end_ns)
        return params

    @staticmethod
    def _parse(payload: Any) -> list[LogEntry]:
        """Flatten Loki's per-stream response into one ascending sequence.

        Always ascending, whichever `direction` was requested. Loki returns
        `backward` results newest-first, and a caller that forgot to reverse
        them would print a batch upside down -- a bug that is invisible in a
        one-line test and obvious only in production. Normalising here removes
        the possibility rather than documenting it.

        Sorted by ``(timestamp, line)``: an integer key, never a float, and the
        line as a tiebreaker so a batch's order is deterministic when several
        lines share a nanosecond.
        """
        if not isinstance(payload, dict):
            raise LokiException("Log store returned a malformed response")
        data = payload.get("data") or {}
        result = data.get("result") or []
        entries: list[LogEntry] = []
        for stream in result:
            labels = stream.get("stream") or {}
            for value in stream.get("values") or []:
                # Loki's shape is [timestamp, line]; anything else is a
                # protocol change we should notice rather than silently drop.
                if not isinstance(value, (list, tuple)) or len(value) < 2:
                    raise LokiException("Log store returned a malformed log entry")
                entries.append(
                    LogEntry(timestamp_ns=str(value[0]), line=value[1], labels=dict(labels))
                )
        entries.sort(key=lambda e: (int(e.timestamp_ns), e.line))
        return entries

    def _check(self, response: httpx.Response) -> Any:
        if response.status_code < 200 or response.status_code >= 300:
            # Loki's body says *why*; without it the caller sees a bare status
            # and a user sees an error nobody can act on.
            raise LokiException(
                f"Log store query returned HTTP {response.status_code}: "
                f"{response.text.strip()[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LokiException("Log store returned a non-JSON response") from exc

    # --- the one call, twice ----------------------------------------------

    def query_range(
        self,
        *,
        query: str,
        start_ns: int,
        end_ns: int | None = None,
        limit: int,
        direction: str = DIRECTION_FORWARD,
    ) -> list[LogEntry]:
        """Run one range query. Returns entries ascending by timestamp."""
        params = self._params(
            query=query, start_ns=start_ns, end_ns=end_ns, limit=limit, direction=direction
        )
        url = f"{self._base_url}{QUERY_RANGE_PATH}"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params)
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise LokiException(f"Log store is unreachable: {exc}") from exc
        return self._parse(self._check(response))

    async def aquery_range(
        self,
        *,
        query: str,
        start_ns: int,
        end_ns: int | None = None,
        limit: int,
        direction: str = DIRECTION_FORWARD,
    ) -> list[LogEntry]:
        """`query_range`, for the streaming endpoint's event loop."""
        params = self._params(
            query=query, start_ns=start_ns, end_ns=end_ns, limit=limit, direction=direction
        )
        url = f"{self._base_url}{QUERY_RANGE_PATH}"
        try:
            if self._async_client is not None:
                response = await self._async_client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise LokiException(f"Log store is unreachable: {exc}") from exc
        return self._parse(self._check(response))
