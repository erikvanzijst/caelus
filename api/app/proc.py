from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Callable, Literal

ErrorCategory = Literal["retryable", "fatal"]
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

_RETRYABLE_PATTERNS = (
    "timed out",
    "timeout",
    "temporarily unavailable",
    "connection refused",
    "connection reset",
    "i/o timeout",
    "tls handshake timeout",
    "context deadline exceeded",
    "unable to connect",
    "too many requests",
    "rate limit",
)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


class AdapterCommandError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        result: CommandResult,
        category: ErrorCategory,
    ) -> None:
        self.result = result
        self.category = category
        super().__init__(self._build_message(message))

    @property
    def retryable(self) -> bool:
        return self.category == "retryable"

    def _build_message(self, message: str) -> str:
        detail = (self.result.stderr or self.result.stdout).strip()
        if len(detail) > 400:
            detail = f"{detail[:397]}..."
        cmd = " ".join(self.result.command)
        return (
            f"{message} (category={self.category}, returncode={self.result.returncode}, "
            f"command={cmd!r}, detail={detail!r})"
        )


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def classify_error(*, returncode: int, stderr: str, stdout: str) -> ErrorCategory:
    if returncode < 0:
        return "retryable"
    text = f"{stderr}\n{stdout}".lower()
    if any(pattern in text for pattern in _RETRYABLE_PATTERNS):
        return "retryable"
    return "fatal"


def run_command(
    command: list[str],
    *,
    runner: CommandRunner | None = None,
    error_message: str,
) -> CommandResult:
    active_runner = runner or default_runner
    completed = active_runner(command)
    result = CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if result.returncode != 0:
        raise AdapterCommandError(
            message=error_message,
            result=result,
            category=classify_error(
                returncode=result.returncode,
                stderr=result.stderr,
                stdout=result.stdout,
            ),
        )
    return result
