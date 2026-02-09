from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProvisionResult:
    success: bool
    message: str


class Provisioner:
    def provision(self, *, deployment_id: int) -> ProvisionResult:
        # Stub implementation to be replaced with Kubernetes/Helm integration.
        return ProvisionResult(success=True, message=f"Queued provisioning for {deployment_id}")


provisioner = Provisioner()
