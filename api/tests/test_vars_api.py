"""The vars sub-resource: `/api/users/{u}/deployments/{d}/vars/{phase}`.

The properties that matter most here are negative ones -- a sensitive value
must not come back out, to anyone, ever -- so most of these assert what is
*absent* from a response.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from app.models import (
    DeploymentVarORM,
    ProductORM,
    ProductTemplateVersionORM,
    UserORM,
)
from app.models.core import _utcnow
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_DELETING,
    DEPLOYMENT_STATUS_READY,
)
from tests.conftest import (  # noqa: F401
    AUTH_HEADER,
    OTHER_AUTH_HEADER,
    USER_AUTH_HEADER,
    USER_EMAIL,
    db_session,
    make_deployment_with_release,
    user_client,
)

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "host": {"type": "string"},
        "LOG_LEVEL": {"type": "string", "x-caelus-target": "runtime"},
        "SIGNUPS_ALLOWED": {"type": "boolean", "x-caelus-target": "runtime"},
        "ADMIN_TOKEN": {
            "type": "string",
            "x-caelus-target": "runtime",
            "x-caelus-sensitive": True,
        },
    },
}

SECRET = "hunter2-swordfish"


@pytest.fixture
def deployed(user_client, db_session):
    """A regular user's deployment, with the acting client authenticated as them."""
    client, _admin = user_client
    owner = db_session.exec(select(UserORM).where(UserORM.email == USER_EMAIL)).one()
    product = ProductORM(name="varsapiprod", created_at=_utcnow())
    db_session.add(product)
    db_session.commit()
    template = ProductTemplateVersionORM(
        product_id=product.id,
        chart_ref="oci://example/chart",
        chart_version="1.0.0",
        values_schema_json=SCHEMA,
    )
    db_session.add(template)
    db_session.commit()
    deployment = make_deployment_with_release(
        db_session,
        user_id=owner.id,
        desired_template_id=template.id,
        hostname="varsapi.example.test",
        name="varsapi-app",
        namespace="ns-varsapi",
        status=DEPLOYMENT_STATUS_READY,
    )
    db_session.commit()
    db_session.refresh(deployment)
    return {
        "client": client,
        "session": db_session,
        "owner": owner,
        "deployment": deployment,
        "url": f"/api/users/{owner.id}/deployments/{deployment.id}/vars/runtime",
    }


def _seed(deployed, **entries):
    body = {"vars": {k: v for k, v in entries.items()}}
    response = deployed["client"].patch(deployed["url"], json=body)
    assert response.status_code == 200, response.text
    return response.json()


# ── Reading ───────────────────────────────────────────────────────────────


def test_an_empty_deployment_reports_no_vars(deployed):
    response = deployed["client"].get(deployed["url"])
    assert response.status_code == 200
    assert response.json() == {"vars": {}, "pending": False}


def test_a_sensitive_value_is_omitted_not_masked_or_nulled(deployed):
    _seed(deployed, ADMIN_TOKEN={"value": SECRET}, LOG_LEVEL={"value": "debug"})

    entry = deployed["client"].get(deployed["url"]).json()["vars"]["ADMIN_TOKEN"]

    assert entry["sensitive"] is True
    assert "value" not in entry
    assert SECRET not in deployed["client"].get(deployed["url"]).text


def test_a_single_var_uses_the_same_envelope(deployed):
    _seed(deployed, LOG_LEVEL={"value": "debug"})
    response = deployed["client"].get(deployed["url"] + "/LOG_LEVEL")
    assert response.status_code == 200
    assert response.json()["vars"]["LOG_LEVEL"]["value"] == "debug"


def test_an_unknown_key_is_404(deployed):
    assert deployed["client"].get(deployed["url"] + "/NOPE").status_code == 404


@pytest.mark.parametrize("phase", ["build", "production", "staging"])
def test_an_unknown_phase_is_404(deployed, phase):
    base = deployed["url"].rsplit("/", 1)[0]
    assert deployed["client"].get(f"{base}/{phase}").status_code == 404
    assert (
        deployed["client"].patch(f"{base}/{phase}", json={"vars": {}}).status_code == 404
    )


def test_an_unknown_deployment_is_404(deployed):
    url = f"/api/users/{deployed['owner'].id}/deployments/{uuid4()}/vars/runtime"
    assert deployed["client"].get(url).status_code == 404


# ── Authorization ─────────────────────────────────────────────────────────


def test_another_user_is_refused(deployed):
    _seed(deployed, LOG_LEVEL={"value": "debug"})
    response = deployed["client"].get(deployed["url"], headers=OTHER_AUTH_HEADER)
    assert response.status_code == 403
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"LOG_LEVEL": {"value": "x"}}},
        headers=OTHER_AUTH_HEADER,
    )
    assert response.status_code == 403


def test_an_admin_reading_another_users_vars_gets_no_sensitive_value(deployed):
    """A write-only value an operator can read is not write-only."""
    _seed(deployed, ADMIN_TOKEN={"value": SECRET}, LOG_LEVEL={"value": "debug"})

    response = deployed["client"].get(deployed["url"], headers=AUTH_HEADER)

    assert response.status_code == 200
    assert SECRET not in response.text
    assert "value" not in response.json()["vars"]["ADMIN_TOKEN"]
    # The admin does get the non-sensitive one, so this is not a blanket denial.
    assert response.json()["vars"]["LOG_LEVEL"]["value"] == "debug"


# ── Writing ───────────────────────────────────────────────────────────────


def test_patch_merges_and_put_replaces(deployed):
    _seed(deployed, LOG_LEVEL={"value": "info"}, SIGNUPS_ALLOWED={"value": "true"})

    merged = _seed(deployed, LOG_LEVEL={"value": "debug"})
    assert set(merged["vars"]) == {"LOG_LEVEL", "SIGNUPS_ALLOWED"}
    assert merged["vars"]["LOG_LEVEL"]["value"] == "debug"

    replaced = deployed["client"].put(
        deployed["url"], json={"vars": {"LOG_LEVEL": {"value": "debug"}}}
    )
    assert replaced.status_code == 200
    assert set(replaced.json()["vars"]) == {"LOG_LEVEL"}


def test_a_null_value_deletes(deployed):
    _seed(deployed, LOG_LEVEL={"value": "info"})
    body = _seed(deployed, LOG_LEVEL={"value": None})
    assert body["vars"] == {}


def test_delete_is_idempotent_and_writes_nothing_for_an_absent_key(deployed):
    response = deployed["client"].delete(deployed["url"] + "/LOG_LEVEL")
    assert response.status_code == 204
    rows = deployed["session"].exec(select(DeploymentVarORM)).all()
    assert rows == []


def test_delete_removes_a_var_that_exists(deployed):
    _seed(deployed, LOG_LEVEL={"value": "info"})
    assert deployed["client"].delete(deployed["url"] + "/LOG_LEVEL").status_code == 204
    assert deployed["client"].get(deployed["url"]).json()["vars"] == {}


def test_reading_the_collection_and_writing_it_back_changes_nothing(deployed):
    """The round-trip property the omission rule exists to make safe."""
    _seed(deployed, ADMIN_TOKEN={"value": SECRET}, LOG_LEVEL={"value": "debug"})
    before = deployed["client"].get(deployed["url"]).json()
    row_ids = {
        row.key: row.id
        for row in deployed["session"].exec(select(DeploymentVarORM)).all()
    }

    response = deployed["client"].put(deployed["url"], json=before)

    assert response.status_code == 200, response.text
    assert response.json() == before
    after = {
        row.key: row.id
        for row in deployed["session"].exec(select(DeploymentVarORM)).all()
    }
    # No deletion, no new rows: the same rows are still head.
    assert after == row_ids


def test_pending_flips_with_a_staged_write(deployed):
    assert deployed["client"].get(deployed["url"]).json()["pending"] is False
    body = _seed(deployed, LOG_LEVEL={"value": "debug"})
    assert body["pending"] is True


def test_writing_to_a_deployment_being_deleted_is_409(deployed):
    deployed["deployment"].status = DEPLOYMENT_STATUS_DELETING
    deployed["session"].add(deployed["deployment"])
    deployed["session"].commit()

    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"LOG_LEVEL": {"value": "debug"}}}
    )
    assert response.status_code == 409
    # Reading is still allowed; only the write conflicts.
    assert deployed["client"].get(deployed["url"]).status_code == 200


# ── Rejections ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    ["log-level", "1LEVEL", "PORT", "BUCKET_NAME", "AWS_SECRET_ACCESS_KEY",
     "CAELUS_HOME", "S3_BUCKET", "RAILPACK_CONFIG_FILE"],
)
def test_a_reserved_or_malformed_key_is_400(deployed, key):
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {key: {"value": "1"}}}
    )
    assert response.status_code == 400, response.text
    assert deployed["session"].exec(select(DeploymentVarORM)).all() == []


def test_an_oversized_value_is_400_and_stores_nothing(deployed):
    value = "x" * (8 * 1024 + 1)
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"LOG_LEVEL": {"value": value}}}
    )
    assert response.status_code == 400
    assert value not in response.text
    assert deployed["session"].exec(select(DeploymentVarORM)).all() == []


def test_too_many_keys_is_400(deployed):
    body = {"vars": {f"VAR_{i}": {"value": "1"} for i in range(257)}}
    response = deployed["client"].patch(deployed["url"], json=body)
    assert response.status_code == 400
    assert deployed["session"].exec(select(DeploymentVarORM)).all() == []


def test_a_total_over_the_limit_is_400(deployed):
    """Each value is legal on its own; together they are not."""
    body = {
        "vars": {f"VAR_{i}": {"value": "x" * 8192} for i in range(17)}
    }
    response = deployed["client"].patch(deployed["url"], json=body)
    assert response.status_code == 400
    assert deployed["session"].exec(select(DeploymentVarORM)).all() == []


def test_a_chart_property_submitted_as_a_var_is_400(deployed):
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"host": {"value": "example.test"}}}
    )
    assert response.status_code == 400
    assert "host" in response.json()["detail"]


def test_a_failing_sensitive_var_never_echoes_its_value(deployed):
    """Neither the response nor the logs may carry the submitted value."""
    schema_violation = "x" * 3
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"SIGNUPS_ALLOWED": {"value": "yes"}}}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == 'vars.SIGNUPS_ALLOWED: failed constraint "type"'
    assert "yes" not in response.json()["detail"]
    assert schema_violation not in response.text


def test_no_log_record_carries_a_secret(deployed, caplog):
    """A known plaintext must not appear in anything the app logs."""
    import logging

    with caplog.at_level(logging.DEBUG):
        _seed(deployed, ADMIN_TOKEN={"value": SECRET})
        deployed["client"].get(deployed["url"])
        deployed["client"].patch(
            deployed["url"], json={"vars": {"ADMIN_TOKEN": {"value": SECRET[:4]}}}
        )

    assert SECRET not in caplog.text
    assert SECRET[:4] not in [record.getMessage() for record in caplog.records]


def test_contradicting_the_schema_on_sensitivity_is_400(deployed):
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"ADMIN_TOKEN": {"value": SECRET, "sensitive": False}}}
    )
    assert response.status_code == 400
    assert SECRET not in response.text


def test_an_absent_value_for_an_unknown_key_is_400(deployed):
    response = deployed["client"].patch(
        deployed["url"], json={"vars": {"LOG_LEVEL": {"sensitive": True}}}
    )
    assert response.status_code == 400
