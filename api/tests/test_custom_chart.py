"""Render the `custom` chart and assert the object-storage contract it exposes.

Shells out to a real `helm template`, so these assert what Helm actually
produces — including schema validation, which is the half a Go-template unit
test would miss. Skipped when helm is unavailable; CI runs inside the dev
container, which has it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from app.services.template_values import merge_values_scoped

CHART = Path(__file__).resolve().parents[2] / "products" / "custom" / "chart"
DIGEST = "sha256:" + "a" * 64

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(**values: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART)]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _app_container(docs: list[dict]) -> dict:
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


def _pod_spec(docs: list[dict]) -> dict:
    deployment = next(d for d in docs if d["kind"] == "Deployment")
    return deployment["spec"]["template"]["spec"]


BASE = {
    "hostname": "app.example.test",
    "caelus__owner__id": "1",
}
STORAGE = {
    "objectStorage__enabled": "true",
    "caelus__objectStorage__bucket": "dep-11115310-fc46-4ef4-8808-654a6b7a68f6",
    "caelus__objectStorage__endpoint": "https://blob.example.invalid",
    "caelus__objectStorage__region": "garage",
    "caelus__objectStorage__secretName": "custom-user-app-abc123-object-storage",
}


def test_renders_without_storage_and_projects_nothing():
    """A product that has not opted in renders exactly as it did before."""
    container = _app_container(_render(**BASE))
    assert "envFrom" not in container
    # PORT is still injected; the storage block is additive, not a replacement.
    assert {"name": "PORT", "value": "8080"} in container["env"]


def test_renders_with_storage_and_projects_the_secret():
    container = _app_container(_render(**BASE, **STORAGE, image=f"1@{DIGEST}"))
    assert container["envFrom"] == [
        {"secretRef": {"name": "custom-user-app-abc123-object-storage"}}
    ]


def test_storage_enabled_without_a_secret_name_fails_loudly():
    """A reconciler bug must surface as a deployment error naming the missing
    value, not as a pod that silently starts with no credentials."""
    args = ["helm", "template", "t", str(CHART)]
    for key, value in {**BASE, "objectStorage__enabled": "true"}.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0
    assert "caelus.objectStorage.secretName is required" in result.stderr


def test_no_service_account_token_is_mounted():
    """Defense in depth: the tenant image is untrusted code and has no business
    talking to the Kubernetes API."""
    assert _pod_spec(_render(**BASE))["automountServiceAccountToken"] is False
    assert _pod_spec(_render(**BASE, **STORAGE))["automountServiceAccountToken"] is False


def test_catalog_system_values_are_valid_values_for_this_chart():
    """`system_values` ARE the chart's default Helm values — the catalog's are
    handed to `helm upgrade` verbatim — so anything the catalog declares must
    satisfy the chart's own `values.schema.json`.

    This is the check that was missing when a platform-only flag was put at the
    top level of `system_values`: every unit test passed, and the first thing to
    notice was `helm upgrade` on a real deployment, rejecting it with
    `additional properties 'object_storage' not allowed`.
    """
    catalog = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "products" / "catalog" / "custom.yaml").read_text()
    )

    # Exactly what the reconciler hands to `helm upgrade`: catalog system values
    # as defaults, then the tenant's values, then the system overrides last.
    merged = merge_values_scoped(
        catalog["template"]["system_values"],
        {"hostname": "app.example.test", "image": f"1@{DIGEST}"},
        {
            "caelus": {
                "owner": {"id": 1, "email": "t@example.test"},
                "plan": {"storageBytes": 1073741824, "storageSize": "1Gi"},
                "ingress": {
                    "enabled": True,
                    "host": "app.example.test",
                    "tls": {"wildcard": True},
                },
                "objectStorage": {
                    "bucket": "dep-11115310-fc46-4ef4-8808-654a6b7a68f6",
                    "endpoint": "https://blob.example.invalid",
                    "region": "garage",
                    "secretName": "custom-user-app-abc123-object-storage",
                },
            }
        },
    )

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(merged, f)
        values_path = f.name
    try:
        result = subprocess.run(
            ["helm", "template", "t", str(CHART), "-f", values_path],
            capture_output=True,
            text=True,
        )
    finally:
        Path(values_path).unlink()

    assert result.returncode == 0, (
        "the catalog's system_values are not valid values for this chart:\n" + result.stderr
    )
    assert "additional properties" not in result.stderr


def test_catalog_chart_version_matches_the_chart():
    """The catalog pins a version; a bumped chart with a stale catalog pin
    installs the old chart and the mismatch is invisible until runtime."""
    catalog = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "products" / "catalog" / "custom.yaml").read_text()
    )
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    assert catalog["template"]["chart_version"] == chart["version"]


def test_schema_declares_both_halves_and_requires_neither():
    """`additionalProperties: false` at the top level means the schema has to
    admit these explicitly, and must not require them.

    Two halves, deliberately: the top-level toggle is a static product
    declaration the chart reads, and `caelus.objectStorage` carries the
    per-deployment references the reconciler injects. The toggle must NOT appear
    in the injected half, or there would be two places to set the same thing.
    """
    schema = json.loads((CHART / "values.schema.json").read_text())

    toggle = schema["properties"]["objectStorage"]
    assert set(toggle["properties"]) == {"enabled"}
    assert "objectStorage" not in schema.get("required", [])

    injected = schema["properties"]["caelus"]["properties"]["objectStorage"]
    assert set(injected["properties"]) >= {"bucket", "endpoint", "region", "secretName"}
    assert "enabled" not in injected["properties"]
    assert "required" not in injected
    assert "objectStorage" not in schema["properties"]["caelus"].get("required", [])


def test_the_toggle_is_absent_from_the_tenant_facing_schema():
    """A tenant must not be able to switch object storage on for themselves.

    `user.schema.json` is the tenant-facing contract; the toggle is a system
    value and belongs only in `values.schema.json`.
    """
    user_schema = json.loads((CHART / "user.schema.json").read_text())
    assert "objectStorage" not in user_schema["properties"]
    assert user_schema.get("additionalProperties") is False


def test_the_ownership_assertion_still_holds_with_storage_enabled():
    """Storage must not become a way around the image ownership check."""
    args = ["helm", "template", "t", str(CHART)]
    for key, value in {**BASE, **STORAGE, "image": f"999@{DIGEST}"}.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode != 0
    assert "does not match deployment owner" in result.stderr
