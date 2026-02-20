from __future__ import annotations

from dataclasses import dataclass

from app.proc import (
    AdapterCommandError,
    CommandRunner,
    run_command,
)


@dataclass(frozen=True)
class NamespaceResult:
    name: str
    exists: bool
    changed: bool
    terminating: bool = False


class KubeAdapter:
    """Adapter for namespace lifecycle operations."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self._runner = runner

    def ensure_namespace(self, name: str) -> NamespaceResult:
        if self.namespace_exists(name):
            return NamespaceResult(name=name, exists=True, changed=False)

        run_command(
            ["kubectl", "create", "namespace", name],
            runner=self._runner,
            error_message=f"Failed to create namespace {name}",
        )
        return NamespaceResult(name=name, exists=True, changed=True)

    def delete_namespace(self, name: str) -> NamespaceResult:
        try:
            run_command(
                ["kubectl", "delete", "namespace", name, "--ignore-not-found=true"],
                runner=self._runner,
                error_message=f"Failed to delete namespace {name}",
            )
            return NamespaceResult(name=name, exists=False, changed=True)
        except AdapterCommandError as exc:
            if "not found" in exc.result.stderr.lower():
                return NamespaceResult(name=name, exists=False, changed=False)
            raise

    def namespace_exists(self, name: str) -> bool:
        try:
            run_command(
                ["kubectl", "get", "namespace", name, "-o", "name"],
                runner=self._runner,
                error_message=f"Failed to check namespace {name}",
            )
            return True
        except AdapterCommandError as exc:
            text = f"{exc.result.stderr}\n{exc.result.stdout}".lower()
            if "not found" in text:
                return False
            raise

    def namespace_terminating(self, name: str) -> bool:
        try:
            result = run_command(
                [
                    "kubectl",
                    "get",
                    "namespace",
                    name,
                    "-o",
                    "jsonpath={.status.phase}",
                ],
                runner=self._runner,
                error_message=f"Failed to inspect namespace {name}",
            )
            return result.stdout.strip().lower() == "terminating"
        except AdapterCommandError as exc:
            text = f"{exc.result.stderr}\n{exc.result.stdout}".lower()
            if "not found" in text:
                return False
            raise
