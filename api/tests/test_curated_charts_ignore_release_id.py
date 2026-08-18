"""The seven curated charts are handed `caelus.releaseId` and ignore it.

The reconciler supplies the value to *every* product with no per-product
condition — rendering it is each chart's decision, and only `custom` renders it.
This asserts the other half of that: a chart that ignores the value applies
normally and its pods carry no release label, so the deployment's logs stay
fully readable at `{namespace, instance}` granularity with only release pinning
unavailable.

Schema rejection was never the risk — every curated chart sets
`caelus.additionalProperties: true` and `mattermost` has no schema at all — so
what this confirms is the *render* path.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


PRODUCTS = Path(__file__).resolve().parents[2] / "products"
RELEASE_ID = "3f2a9c14-0b6d-4e18-9a77-5c1e8d4b2f60"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

# The minimum each chart needs to render standalone, unrelated to this change:
# values a real deployment always has and a bare `helm template` does not.
CURATED = {
    "helloworld": {},
    "immich": {},
    "matrix": {},
    "mattermost": {"caelus.plan.storageSize": "1Gi"},
    "naas": {},
    "nextcloud": {},
    "vaultwarden": {"host": "v.example.test", "caelus.owner.email": "owner@example.test"},
}


def _render(chart: str, values: dict[str, str]) -> str:
    args = ["helm", "template", "t", str(PRODUCTS / chart / "chart")]
    for key, value in values.items():
        args += ["--set", f"{key}={value}"]
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, f"{chart}: {result.stderr}"
    return result.stdout


@pytest.mark.parametrize("chart", sorted(CURATED))
def test_a_curated_chart_applies_while_ignoring_the_release_id(chart):
    baseline = CURATED[chart]
    with_id = _render(chart, {**baseline, "caelus.releaseId": RELEASE_ID})

    # It rendered, and no pod carries a release label.
    assert "caelus.dev/release-id" not in with_id
    for doc in yaml.safe_load_all(with_id):
        if not doc:
            continue
        labels = (
            doc.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
            if isinstance(doc.get("spec"), dict)
            else {}
        )
        assert "caelus.dev/release-id" not in (labels or {})


def _pod_template_labels(rendered: str) -> list[dict]:
    """Every workload pod template's labels, in document order."""
    out = []
    for doc in yaml.safe_load_all(rendered):
        if not isinstance(doc, dict) or doc.get("kind") not in {
            "Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"
        }:
            continue
        spec = doc.get("spec") or {}
        template = (
            spec.get("jobTemplate", {}).get("spec", {}).get("template")
            if doc["kind"] == "CronJob"
            else spec.get("template")
        ) or {}
        out.append((template.get("metadata") or {}).get("labels") or {})
    return out


@pytest.mark.parametrize("chart", sorted(CURATED))
def test_the_release_id_does_not_change_a_curated_pod_template(chart):
    """A chart that ignores the value produces the same pod template with and
    without it, so its deployments keep their existing Helm no-op behaviour --
    only `custom` pays the redeploy-cycles-pods cost.

    Compared at the pod template rather than over the whole render: several of
    these charts generate a random secret on every render, so a byte comparison
    would fail on noise unrelated to this change.
    """
    baseline = CURATED[chart]
    without = _pod_template_labels(_render(chart, baseline))
    with_id = _pod_template_labels(
        _render(chart, {**baseline, "caelus.releaseId": RELEASE_ID})
    )
    assert without == with_id
    assert without, f"{chart} rendered no workload pod template to compare"
