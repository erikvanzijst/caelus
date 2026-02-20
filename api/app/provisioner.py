from __future__ import annotations

from typing import Any

from app.services.helm_adapter import (
    HelmAdapter,
    HelmReleaseOperationResult,
    HelmReleaseStatusResult,
)
from app.services.kube_adapter import KubeAdapter, NamespaceResult


class Provisioner:
    """Facade over Kubernetes/Helm adapters used by reconcile logic."""

    def __init__(self, *, kube: KubeAdapter | None = None, helm: HelmAdapter | None = None) -> None:
        self.kube = kube or KubeAdapter()
        self.helm = helm or HelmAdapter()

    def ensure_namespace(self, *, name: str) -> NamespaceResult:
        return self.kube.ensure_namespace(name)

    def delete_namespace(self, *, name: str) -> NamespaceResult:
        return self.kube.delete_namespace(name)

    def namespace_exists(self, *, name: str) -> bool:
        return self.kube.namespace_exists(name)

    def namespace_terminating(self, *, name: str) -> bool:
        return self.kube.namespace_terminating(name)

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
