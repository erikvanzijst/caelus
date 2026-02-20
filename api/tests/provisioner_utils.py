from __future__ import annotations


class FakeProvisioner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.raise_on_upgrade: Exception | None = None

    def ensure_namespace(self, *, name: str):
        self.calls.append(("ensure_namespace", {"name": name}))
        return None

    def helm_upgrade_install(
        self,
        *,
        release_name: str,
        namespace: str,
        chart_ref: str,
        chart_version: str,
        chart_digest: str | None,
        values: dict,
        timeout: int,
        atomic: bool,
        wait: bool,
    ):
        self.calls.append(
            (
                "helm_upgrade_install",
                {
                    "release_name": release_name,
                    "namespace": namespace,
                    "chart_ref": chart_ref,
                    "chart_version": chart_version,
                    "chart_digest": chart_digest,
                    "values": values,
                    "timeout": timeout,
                    "atomic": atomic,
                    "wait": wait,
                },
            )
        )
        if self.raise_on_upgrade is not None:
            raise self.raise_on_upgrade
        return None

    def helm_uninstall(self, *, release_name: str, namespace: str, timeout: int, wait: bool):
        self.calls.append(
            (
                "helm_uninstall",
                {"release_name": release_name, "namespace": namespace, "timeout": timeout, "wait": wait},
            )
        )
        return None

    def delete_namespace(self, *, name: str):
        self.calls.append(("delete_namespace", {"name": name}))
        return None
