"""SFTP reachability does not depend on the application container's health.

A pod whose app container is crash-looping is `NotReady`, and a Service excludes
`NotReady` pods from its endpoints -- so the SFTP sidecar beside that app
container, running perfectly well, became unreachable at exactly the moment the
tenant most wants their files. The fix is one field on one Service, and its loss
would be **silent**: everything keeps working until an app crash-loops, which is
when nobody is looking at the Service. That is what this test is for.

Its companion is the sidecar's liveness probe. With readiness no longer gating
routing, nothing else stops connections being routed to a wedged `sshd`, so the
probe is load-bearing rather than decorative -- and it must stay a bare TCP
check that touches neither the app container, the exposed PVCs, nor any
credential.

All six consumers are asserted rather than one, because the flag lives in the
library chart but ships as six independently versioned artifacts: a product that
falls behind on the vendored library is the realistic way this regresses.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


PRODUCTS = Path(__file__).resolve().parents[2] / "products"
SSH_PORT = 2222

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

# The six charts that consume `caelus-sftp`, with the minimum values each needs
# to render standalone -- values a real deployment always has and a bare
# `helm template` does not. Unrelated to this change.
CONSUMERS = {
    "helloworld": {},
    "immich": {},
    "lemmy": {},
    "mattermost": {"caelus.plan.storageSize": "1Gi"},
    "nextcloud": {},
    "vaultwarden": {"host": "v.example.test", "caelus.owner.email": "owner@example.test"},
}


@pytest.fixture(scope="module", autouse=True)
def _resolved_dependencies():
    """Vendor each chart's `caelus-sftp` dependency before anything renders.

    `charts/` is a build artifact -- `products/.gitignore` ignores `**/*.tgz`,
    so a clean checkout has none and `helm template` refuses the chart. `build`
    rather than `update`, so the tracked `Chart.lock` decides what is vendored
    and is not rewritten; that lock is what pins the library version this test
    is really asserting about.
    """
    for chart in CONSUMERS:
        chart_dir = PRODUCTS / chart / "chart"
        result = subprocess.run(
            ["helm", "dependency", "build", str(chart_dir)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{chart}: {result.stderr}"


def _render(chart: str) -> list[dict]:
    args = ["helm", "template", "t", str(PRODUCTS / chart / "chart")]
    for key, value in CONSUMERS[chart].items():
        args += ["--set", f"{key}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, f"{chart}: {result.stderr}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def _sftp_service(docs: list[dict]) -> dict:
    """The Service fronting the sidecar: a Service with a port on 2222."""
    services = [
        doc
        for doc in docs
        if doc.get("kind") == "Service"
        and any(p.get("port") == SSH_PORT for p in (doc.get("spec") or {}).get("ports") or [])
    ]
    assert len(services) == 1, f"expected exactly one SFTP Service, got {len(services)}"
    return services[0]


def _containers(docs: list[dict]) -> list[dict]:
    """Every container in every workload pod template, in document order."""
    out = []
    for doc in docs:
        if doc.get("kind") not in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
            continue
        spec = doc.get("spec") or {}
        template = (
            (spec.get("jobTemplate") or {}).get("spec", {}).get("template")
            if doc["kind"] == "CronJob"
            else spec.get("template")
        ) or {}
        pod = template.get("spec") or {}
        out += (pod.get("containers") or []) + (pod.get("initContainers") or [])
    return out


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_the_sftp_service_publishes_not_ready_addresses(chart):
    """The endpoints include the pod whenever it exists, ready or not."""
    service = _sftp_service(_render(chart))
    assert service["spec"].get("publishNotReadyAddresses") is True, (
        f"{chart}: the SFTP Service does not publish not-ready addresses, so a "
        "deployment whose app container is crash-looping is unreachable over SFTP"
    )


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_the_sidecar_is_probed_on_its_ssh_port(chart):
    """Both probes are plain TCP checks on 2222 -- no exec, no credentials."""
    sidecars = [c for c in _containers(_render(chart)) if c.get("name") == "sftp"]
    assert len(sidecars) == 1, f"{chart}: expected one sftp container, got {len(sidecars)}"
    sidecar = sidecars[0]

    for probe_name in ("startupProbe", "livenessProbe"):
        probe = sidecar.get(probe_name)
        assert probe, f"{chart}: the sftp container declares no {probe_name}"
        assert set(probe) & {"exec", "httpGet"} == set(), (
            f"{chart}: the sftp {probe_name} must be a bare TCP check -- an exec "
            "probe couples liveness to the container's own state, and an SFTP "
            "session would couple it to the credentials Secret"
        )
        assert probe.get("tcpSocket", {}).get("port") == SSH_PORT

    # The startup probe exists to hold liveness off while atmoz/sftp generates
    # host keys, which it does on every start. Too short a budget and the
    # sidecar is killed mid-keygen and loops forever.
    startup = sidecar["startupProbe"]
    budget = startup.get("periodSeconds", 10) * startup.get("failureThreshold", 3)
    assert budget >= 60, (
        f"{chart}: {budget}s is not enough headroom for RSA-4096 host-key generation"
    )


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_no_other_container_is_probed_on_the_ssh_port(chart):
    """The probes belong to the sidecar and were not spliced anywhere else."""
    for container in _containers(_render(chart)):
        if container.get("name") == "sftp":
            continue
        for probe_name in ("startupProbe", "livenessProbe", "readinessProbe"):
            probe = container.get(probe_name) or {}
            assert probe.get("tcpSocket", {}).get("port") != SSH_PORT, (
                f"{chart}: container {container.get('name')!r} carries a "
                f"{probe_name} on the SFTP port"
            )
