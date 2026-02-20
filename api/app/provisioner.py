from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.proc import AdapterCommandError, CommandRunner, run_command


@dataclass(frozen=True)
class NamespaceResult:
    name: str
    exists: bool
    changed: bool


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



@dataclass(frozen=True)
class HelmReleaseOperationResult:
    release_name: str
    namespace: str
    changed: bool
    status: str | None = None
    revision: int | None = None


@dataclass(frozen=True)
class HelmReleaseStatusResult:
    release_name: str
    namespace: str
    exists: bool
    status: str | None = None
    revision: int | None = None
    raw: dict[str, Any] | None = None


class HelmAdapter:
    """Adapter for Helm release lifecycle operations."""

    def __init__(self, *, runner: CommandRunner | None = None) -> None:
        self._runner = runner

    def helm_upgrade_install(
        self,
        *,
        release_name: str,
        namespace: str,
        chart_ref: str,
        chart_version: str,
        chart_digest: str | None,
        values: dict[str, Any],
        timeout: int,
        atomic: bool,
        wait: bool,
    ) -> HelmReleaseOperationResult:
        resolved_chart = _with_optional_digest(chart_ref=chart_ref, chart_digest=chart_digest)
        with _values_file(values) as values_file:
            cmd = [
                "helm",
                "upgrade",
                "--install",
                release_name,
                resolved_chart,
                "--namespace",
                namespace,
                "--version",
                chart_version,
                "--timeout",
                f"{timeout}s",
                "--values",
                str(values_file),
            ]
            if atomic:
                cmd.append("--atomic")
            if wait:
                cmd.append("--wait")

            run_command(
                cmd,
                runner=self._runner,
                error_message=f"Failed to upgrade/install release {release_name}",
            )

        status = self.helm_get_release_status(release_name=release_name, namespace=namespace)
        return HelmReleaseOperationResult(
            release_name=release_name,
            namespace=namespace,
            changed=True,
            status=status.status,
            revision=status.revision,
        )

    def helm_uninstall(
        self,
        *,
        release_name: str,
        namespace: str,
        timeout: int,
        wait: bool,
    ) -> HelmReleaseOperationResult:
        cmd = [
            "helm",
            "uninstall",
            release_name,
            "--namespace",
            namespace,
            "--timeout",
            f"{timeout}s",
        ]
        if wait:
            cmd.append("--wait")
        try:
            run_command(
                cmd,
                runner=self._runner,
                error_message=f"Failed to uninstall release {release_name}",
            )
            return HelmReleaseOperationResult(
                release_name=release_name,
                namespace=namespace,
                changed=True,
                status="uninstalled",
            )
        except AdapterCommandError as exc:
            text = f"{exc.result.stderr}\n{exc.result.stdout}".lower()
            if "release: not found" in text or "not found" in text:
                return HelmReleaseOperationResult(
                    release_name=release_name,
                    namespace=namespace,
                    changed=False,
                    status="not-found",
                )
            raise

    def helm_get_release_status(self, *, release_name: str, namespace: str) -> HelmReleaseStatusResult:
        try:
            result = run_command(
                ["helm", "status", release_name, "--namespace", namespace, "--output", "json"],
                runner=self._runner,
                error_message=f"Failed to fetch release status for {release_name}",
            )
        except AdapterCommandError as exc:
            text = f"{exc.result.stderr}\n{exc.result.stdout}".lower()
            if "release: not found" in text or "not found" in text:
                return HelmReleaseStatusResult(release_name=release_name, namespace=namespace, exists=False)
            raise

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from helm status for release {release_name}") from exc

        info = payload.get("info", {}) if isinstance(payload, dict) else {}
        status = info.get("status") if isinstance(info, dict) else None
        revision = payload.get("version") if isinstance(payload, dict) else None
        if not isinstance(revision, int):
            revision = None

        return HelmReleaseStatusResult(
            release_name=release_name,
            namespace=namespace,
            exists=True,
            status=status if isinstance(status, str) else None,
            revision=revision,
            raw=payload if isinstance(payload, dict) else None,
        )


def _with_optional_digest(*, chart_ref: str, chart_digest: str | None) -> str:
    if not chart_digest or "@" in chart_ref:
        return chart_ref
    return f"{chart_ref}@{chart_digest}"


class _values_file:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values
        self._tmp: NamedTemporaryFile[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> Path:
        tmp = NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        tmp.write(json.dumps(self._values))
        tmp.flush()
        tmp.close()
        self._tmp = tmp
        self.path = Path(tmp.name)
        return self.path

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.path and self.path.exists():
            self.path.unlink()


class Provisioner:
    """Facade over Kubernetes/Helm adapters used by reconcile logic."""

    def __init__(self, *, kube: KubeAdapter | None = None, helm: HelmAdapter | None = None) -> None:
        self.kube = kube or KubeAdapter()
        self.helm = helm or HelmAdapter()

    # TODO: these namespace functions should not be exposed -- namespace creation/deletion should be done by the install/uninstall methods transparently
    def ensure_namespace(self, *, name: str) -> NamespaceResult:
        return self.kube.ensure_namespace(name)

    def delete_namespace(self, *, name: str) -> NamespaceResult:
        return self.kube.delete_namespace(name)

    def namespace_exists(self, *, name: str) -> bool:
        return self.kube.namespace_exists(name)

    def helm_upgrade_install(
        self,
        *,
        release_name: str,
        namespace: str,
        chart_ref: str,
        chart_version: str,
        chart_digest: str | None,
        values: dict[str, Any],
        timeout: int,
        atomic: bool,
        wait: bool,
    ) -> HelmReleaseOperationResult:
        return self.helm.helm_upgrade_install(
            release_name=release_name,
            namespace=namespace,
            chart_ref=chart_ref,
            chart_version=chart_version,
            chart_digest=chart_digest,
            values=values,
            timeout=timeout,
            atomic=atomic,
            wait=wait,
        )

    def helm_uninstall(
        self,
        *,
        release_name: str,
        namespace: str,
        timeout: int,
        wait: bool,
    ) -> HelmReleaseOperationResult:
        return self.helm.helm_uninstall(
            release_name=release_name,
            namespace=namespace,
            timeout=timeout,
            wait=wait,
        )

    def helm_get_release_status(
        self,
        *,
        release_name: str,
        namespace: str,
    ) -> HelmReleaseStatusResult:
        return self.helm.helm_get_release_status(release_name=release_name, namespace=namespace)


provisioner = Provisioner()
