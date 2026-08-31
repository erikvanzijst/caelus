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

# The six charts that consume `ssh-sidecar`, with the minimum values each needs
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

# The platform's public key, injected per environment by the reconciler. The
# chart refuses to render without it.
PLATFORM_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIV5/SURDe/M7JtAheJuxURSGgpFB8Yfrd/LY6c9+DzR platform"


@pytest.fixture(scope="module", autouse=True)
def _resolved_dependencies():
    """Vendor each chart's `ssh-sidecar` dependency before anything renders.

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


def _render(chart: str, *, platform_key: str | None = PLATFORM_KEY) -> list[dict]:
    args = ["helm", "template", "t", str(PRODUCTS / chart / "chart")]
    if platform_key is not None:
        args += ["--set-string", f"caelus.ssh.platformPublicKey={platform_key}"]
    for key, value in CONSUMERS[chart].items():
        args += ["--set", f"{key}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, f"{chart}: {result.stderr}"
    return [doc for doc in yaml.safe_load_all(result.stdout) if isinstance(doc, dict)]


def _sftp_secret(docs: list[dict]) -> dict:
    secrets = [
        doc
        for doc in docs
        if doc.get("kind") == "Secret"
        and (doc.get("metadata", {}).get("labels") or {}).get("caelus.dev/component") == "ssh"
    ]
    assert len(secrets) == 1, f"expected exactly one SFTP Secret, got {len(secrets)}"
    return secrets[0]


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


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_no_routing_object_is_rendered(chart):
    """Routing is resolved per connection; nothing describes it as an object."""
    for doc in _render(chart):
        assert doc.get("kind") != "Pipe", (
            f"{chart}: renders a Pipe. The edge resolves routing from the platform "
            "database, so a routing object here is state nothing reads and nothing reaps"
        )


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_no_password_is_generated(chart):
    """No password in the Secret, and none in the sidecar's user line."""
    data = _sftp_secret(_render(chart)).get("stringData") or {}
    assert "password" not in data, f"{chart}: the SFTP Secret carries a password"

    user_line = data["users.conf"]
    user, password, _, _ = user_line.split(":", 3)
    assert password == "", (
        f"{chart}: users.conf is {user_line!r}; the password field must be empty, which "
        "is what makes atmoz/sftp disable password login for the account"
    )
    assert user == "t", f"{chart}: the sidecar user is {user!r}, not the release name"


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_the_secret_carries_the_platform_public_key_and_nothing_secret(chart):
    data = _sftp_secret(_render(chart)).get("stringData") or {}
    assert data.get("platform_key.pub") == PLATFORM_KEY
    assert set(data) == {"username", "users.conf", "platform_key.pub"}
    for value in data.values():
        assert "PRIVATE KEY" not in value, f"{chart}: private key material in the SFTP Secret"


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_the_sidecar_reads_the_key_from_atmozs_queue_directory(chart):
    """`.ssh/keys/*` is concatenated into authorized_keys with the ownership
    sshd requires; writing authorized_keys directly leaves it root-owned and
    the login fails with nothing but `[preauth]` in the log."""
    docs = _render(chart)
    sidecar = next(c for c in _containers(docs) if c.get("name") == "sftp")
    mounts = {m["mountPath"]: m["name"] for m in sidecar.get("volumeMounts") or []}
    assert "/home/t/.ssh/keys" in mounts, f"{chart}: the platform key is not mounted for atmoz"


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_the_sidecar_disables_password_authentication(chart):
    """Unavailable at sshd, not merely unusable because accounts are locked."""
    configmaps = [
        doc
        for doc in _render(chart)
        if doc.get("kind") == "ConfigMap"
        and (doc.get("metadata", {}).get("labels") or {}).get("caelus.dev/component") == "ssh"
    ]
    assert len(configmaps) == 1
    init = configmaps[0]["data"]["init.sh"]
    assert "PasswordAuthentication no" in init
    assert "KbdInteractiveAuthentication no" in init


@pytest.mark.parametrize("chart", sorted(CONSUMERS))
def test_rendering_fails_without_the_platform_key(chart):
    """A sidecar trusting no key is worse than a chart that refuses to render."""
    args = ["helm", "template", "t", str(PRODUCTS / chart / "chart")]
    for key, value in CONSUMERS[chart].items():
        args += ["--set", f"{key}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0, f"{chart}: rendered with no platform key"
    assert "platformPublicKey" in result.stderr
