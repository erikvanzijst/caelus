"""freepod — the Freepod command-line client.

The package is a pure client of the public Freepod REST API. It shares no code
with the API server and imports nothing from it.

This module holds only the error hierarchy, because every other module raises
from it and a leaf module keeps the imports acyclic. Each error carries the
exit code its class maps onto; see `cli-distribution` § *Exit codes
distinguish failure classes*.
"""

from __future__ import annotations

__all__ = [
    "FreepodError",
    "UsageError",
    "AuthenticationError",
    "PermissionError_",
    "BuildFailed",
    "RolloutFailed",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_USAGE",
    "EXIT_NOT_AUTHENTICATED",
    "EXIT_BUILD_FAILED",
    "EXIT_ROLLOUT_FAILED",
]

__version__ = "0.1.2"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_AUTHENTICATED = 3
EXIT_BUILD_FAILED = 4
EXIT_ROLLOUT_FAILED = 5


class FreepodError(Exception):
    """Anything that should end the run with a readable message.

    Subclasses override `exit_code` to select their row of the exit-code
    table. The base class is the "unexpected error" row.
    """

    exit_code = EXIT_ERROR


class UsageError(FreepodError):
    """The command was invoked wrongly. Nothing was attempted."""

    exit_code = EXIT_USAGE


class AuthenticationError(FreepodError):
    """No usable credential, or one the platform will not accept.

    Raised for the 401 row of the status-code contract, where re-authenticating
    would succeed and change nothing, as well as for the ordinary "you are not
    logged in" case.
    """

    exit_code = EXIT_NOT_AUTHENTICATED


class PermissionError_(FreepodError):
    """Authenticated, but not permitted to act on the resource.

    Named with a trailing underscore so it cannot shadow the builtin. This is
    the API's own 403 — a credential problem no refresh can fix — and it is
    deliberately *not* an `AuthenticationError`, so it never triggers a login.
    """

    exit_code = EXIT_ERROR


class BuildFailed(FreepodError):
    """The build reached a non-successful terminal status."""

    exit_code = EXIT_BUILD_FAILED


class RolloutFailed(FreepodError):
    """The rollout failed, or waiting for it timed out."""

    exit_code = EXIT_ROLLOUT_FAILED
