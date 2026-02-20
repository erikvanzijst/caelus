from __future__ import annotations

from dataclasses import dataclass
import logging
import shlex
import subprocess
from typing import Callable

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]
logger = logging.getLogger(__name__)


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
    logger.info("Running external command: %s", shlex.join(command))
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
        logger.warning(
            "External command failed (returncode=%s):\n%s\n%s",
            result.returncode,
            result.stdout,
            result.stderr
        )
        raise AdapterCommandError(
            message=error_message,
            result=result,
        )
    logger.debug("External command succeeded: %s", shlex.join(command))
    return result
