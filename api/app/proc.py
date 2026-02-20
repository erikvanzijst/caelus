from __future__ import annotations

from dataclasses import dataclass
import subprocess
from typing import Callable

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


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
    ) -> None:
        self.result = result
        super().__init__(self._build_message(message))

    def _build_message(self, message: str) -> str:
        detail = (self.result.stderr or self.result.stdout).strip()
        if len(detail) > 400:
            detail = f"{detail[:397]}..."
        cmd = " ".join(self.result.command)
        return (
            f"{message} (returncode={self.result.returncode}, "
            f"command={cmd!r}, detail={detail!r})"
        )


def default_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


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
        )
    return result
