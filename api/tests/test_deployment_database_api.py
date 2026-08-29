"""A deployment's database connection details, quota state and usage.

Reads only: the endpoint, the `caelus` command and the service under both
answer from the `deployment_database` record, the deployment's plan allowance
and the platform's pooler settings, and write nothing.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from sqlmodel import select

from app.config import get_settings
from app.models import (
    BillingInterval,
    DeploymentDatabaseORM,
    PlanORM,
    PlanTemplateVersionORM,
    ProductORM,
    ProductTemplateVersionORM,
    SubscriptionORM,
    UserORM,
)
from app.models.core import _utcnow
from app.services import deployments as deployment_service
from app.services import relational_storage as rs
from app.services import var_crypto
from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED
from tests.conftest import USER_EMAIL, create_user, make_deployment_with_release

MEGABYTE = 1024 * 1024

POOLER_HOST = "caelus-tenant-pooler.caelus-tenant.svc.cluster.local"
POOLER_PORT = 6432

#: Deliberately not hexadecimal. The generator emits hex today, and a test that
#: leaned on that would pass while the code mishandled anything else.
PASSWORD = "p@ss/w:rd?#[]&=+ 90%"


@pytest.fixture(autouse=True)
def pooler_settings(monkeypatch):
    monkeypatch.setenv("CAELUS_TENANT_DB_POOLER_HOST", POOLER_HOST)
    monkeypatch.setenv("CAELUS_TENANT_DB_POOLER_PORT", str(POOLER_PORT))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _deployment(session, *, user_id: int, enabled: bool = True, database_bytes: int = 100 * MEGABYTE):
    """A deployment whose product opts into relational storage, or does not."""
    token = uuid4().hex[:8]
    product = ProductORM(name=f"db-product-{token}", created_at=_utcnow())
    session.add(product)
    session.commit()

    template = ProductTemplateVersionORM(
        product_id=product.id,
        chart_ref="oci://example/chart",
        chart_version="1.0.0",
        system_values_json={"relationalStorage": {"enabled": enabled}},
    )
    session.add(template)
    session.commit()

    plan = PlanORM(name=f"db-plan-{token}", product_id=product.id, created_at=_utcnow())
    session.add(plan)
    session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=0,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=0,
        database_bytes=database_bytes,
        created_at=_utcnow(),
    )
    session.add(ptv)
    session.flush()
    plan.template_id = ptv.id
    subscription = SubscriptionORM(plan_template_id=ptv.id, user_id=user_id, created_at=_utcnow())
    session.add(subscription)
    session.commit()

    deployment = make_deployment_with_release(
        session,
        user_id=user_id,
        desired_template_id=template.id,
        subscription_id=subscription.id,
        hostname=f"{token}.example.test",
        name=f"app-{token}",
        namespace=f"ns-{token}",
    )
    session.commit()
    session.refresh(deployment)
    return deployment


def _provision_record(session, deployment, *, password: str = PASSWORD, **fields):
    """The row a reconcile would have left behind, without a tenant cluster."""
    ciphertext, key_id = var_crypto.encrypt(password)
    record = DeploymentDatabaseORM(
        deployment_id=deployment.id,
        db_name=rs.database_name(deployment),
        role_name=rs.role_name(deployment),
        password_encrypted=ciphertext,
        key_id=key_id,
        **fields,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _user_id(session, email: str) -> int:
    return session.exec(select(UserORM).where(UserORM.email == email)).one().id


# ── The read model and the service ────────────────────────────────────────


def test_the_owner_gets_every_field(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment, size_bytes=42 * MEGABYTE, measured_at=_utcnow())

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )

    assert details.database == rs.database_name(deployment)
    assert details.role == rs.role_name(deployment)
    assert details.password == PASSWORD
    assert details.password_withheld is False
    assert details.quota_state == rs.QUOTA_OK
    assert details.allowance_bytes == 100 * MEGABYTE
    assert details.size_bytes == 42 * MEGABYTE
    assert details.measured_at is not None


def test_the_address_is_the_poolers_never_the_servers(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment)

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )

    assert (details.host, details.port) == (POOLER_HOST, POOLER_PORT)


def test_no_field_carries_a_composed_url(db_session):
    """The components are the contract; a URL is the forwarding client's job."""
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment)

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )

    assert "url" not in details.model_dump()
    assert not any(
        isinstance(value, str) and "postgresql://" in value
        for value in details.model_dump().values()
    )


def test_a_product_without_relational_storage_has_no_database(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id, enabled=False)

    with pytest.raises(rs.RelationalStorageUnavailableException) as raised:
        deployment_service.get_database_details(
            db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
        )
    assert raised.value.code == "relational_storage_unavailable"


def test_never_measured_is_not_measured_at_zero(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()

    never = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, never)
    empty = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, empty, size_bytes=0, measured_at=_utcnow())

    unmeasured = deployment_service.get_database_details(
        db_session, deployment_id=never.id, user_id=owner.id, viewer_id=owner.id
    )
    measured = deployment_service.get_database_details(
        db_session, deployment_id=empty.id, user_id=owner.id, viewer_id=owner.id
    )

    assert unmeasured.size_bytes is None and unmeasured.measured_at is None
    assert measured.size_bytes == 0 and measured.measured_at is not None


@pytest.mark.parametrize("state", [rs.QUOTA_WARNED, rs.QUOTA_READONLY, rs.QUOTA_BLOCKED])
def test_a_degraded_quota_state_is_reported(db_session, state):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment, quota_state=state)

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )
    assert details.quota_state == state


def test_the_password_is_withheld_from_anyone_but_the_owner(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    reader = UserORM(email=f"admin-{uuid4().hex[:8]}@example.com", is_admin=True)
    db_session.add(owner)
    db_session.add(reader)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment)

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=reader.id
    )

    assert details.password is None
    assert details.password_withheld is True
    assert not any(
        isinstance(value, str) and PASSWORD in value for value in details.model_dump().values()
    )


def test_a_caller_that_cannot_say_who_is_asking_gets_no_secret(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment)

    details = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=None
    )
    assert details.password is None and details.password_withheld is True


def test_reading_changes_nothing(db_session):
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    record = _provision_record(db_session, deployment, quota_state=rs.QUOTA_READONLY)
    before = record.model_dump()

    first = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )
    second = deployment_service.get_database_details(
        db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
    )

    assert first.password == second.password == PASSWORD
    db_session.refresh(record)
    assert record.model_dump() == before
    assert record.quota_state == rs.QUOTA_READONLY


def test_a_deleted_deployment_is_not_found(db_session):
    """Not this service's rule: it is the platform's readable-deployment rule."""
    owner = UserORM(email=f"owner-{uuid4().hex[:8]}@example.com")
    db_session.add(owner)
    db_session.commit()
    deployment = _deployment(db_session, user_id=owner.id)
    _provision_record(db_session, deployment)
    deployment.status = DEPLOYMENT_STATUS_DELETED
    db_session.add(deployment)
    db_session.commit()

    with pytest.raises(Exception) as raised:
        deployment_service.get_database_details(
            db_session, deployment_id=deployment.id, user_id=owner.id, viewer_id=owner.id
        )
    assert not isinstance(raised.value, rs.RelationalStorageUnavailableException)
    assert "not found" in str(raised.value).lower()


# ── The endpoint ──────────────────────────────────────────────────────────


def _api_deployment(client, db_session, *, owner_email: str, enabled: bool = True):
    owner_id = _user_id(db_session, owner_email)
    deployment = _deployment(db_session, user_id=owner_id, enabled=enabled)
    return owner_id, deployment


def test_the_owner_reads_the_details_through_the_api(user_client, db_session):
    client, _admin = user_client
    owner_id, deployment = _api_deployment(client, db_session, owner_email=USER_EMAIL)
    _provision_record(db_session, deployment, size_bytes=7 * MEGABYTE, measured_at=_utcnow())

    resp = client.get(f"/api/users/{owner_id}/deployments/{deployment.id}/database")

    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == POOLER_HOST
    assert body["port"] == POOLER_PORT
    assert body["database"] == rs.database_name(deployment)
    assert body["role"] == rs.role_name(deployment)
    assert body["password"] == PASSWORD
    assert body["password_withheld"] is False
    assert body["allowance_bytes"] == 100 * MEGABYTE
    assert body["size_bytes"] == 7 * MEGABYTE
    assert "url" not in body


def test_an_administrator_reads_everything_but_the_password(client, db_session):
    owner_id = create_user(client, "db-owner@example.com")["id"]
    deployment = _deployment(db_session, user_id=owner_id)
    _provision_record(db_session, deployment)

    resp = client.get(f"/api/users/{owner_id}/deployments/{deployment.id}/database")

    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == rs.database_name(deployment)
    assert body["password"] is None
    assert body["password_withheld"] is True
    assert PASSWORD not in resp.text


def test_a_non_owner_is_refused(user_client, db_session):
    client, admin_user = user_client
    deployment = _deployment(db_session, user_id=admin_user.id)
    _provision_record(db_session, deployment)

    resp = client.get(f"/api/users/{admin_user.id}/deployments/{deployment.id}/database")
    assert resp.status_code == 403


def test_a_product_without_relational_storage_answers_with_a_stable_code(user_client, db_session):
    client, _admin = user_client
    owner_id, deployment = _api_deployment(
        client, db_session, owner_email=USER_EMAIL, enabled=False
    )

    resp = client.get(f"/api/users/{owner_id}/deployments/{deployment.id}/database")

    assert resp.status_code == 404
    assert resp.json()["code"] == "relational_storage_unavailable"


def test_a_deployment_under_the_wrong_owner_is_not_found(client, db_session):
    """An administrator may reach it; the ownership-scoped lookup still refuses."""
    owner_id = create_user(client, "db-owner-2@example.com")["id"]
    other_id = create_user(client, "db-other@example.com")["id"]
    deployment = _deployment(db_session, user_id=owner_id)
    _provision_record(db_session, deployment)

    resp = client.get(f"/api/users/{other_id}/deployments/{deployment.id}/database")

    assert resp.status_code == 404
    assert resp.json().get("code") != "relational_storage_unavailable"


def test_the_password_never_reaches_a_log(user_client, db_session, caplog):
    client, _admin = user_client
    owner_id, deployment = _api_deployment(client, db_session, owner_email=USER_EMAIL)
    _provision_record(db_session, deployment)

    with caplog.at_level(logging.DEBUG):
        ok = client.get(f"/api/users/{owner_id}/deployments/{deployment.id}/database")
        # A failure occurring after the record (and its password) was reached.
        missing = client.get(
            f"/api/users/{owner_id}/deployments/{uuid4()}/database"
        )

    assert ok.status_code == 200 and missing.status_code == 404
    assert PASSWORD not in caplog.text
    assert PASSWORD not in missing.text


# ── `caelus` parity ───────────────────────────────────────────────────────


def _seed_for_cli(*, owner_email: str) -> tuple[int, object]:
    """Seed an owner with a provisioned database through the CLI's own session."""
    from app.db import session_scope

    with session_scope() as session:
        owner = UserORM(email=owner_email)
        session.add(owner)
        session.commit()
        session.refresh(owner)
        deployment = _deployment(session, user_id=owner.id)
        _provision_record(session, deployment, size_bytes=3 * MEGABYTE, measured_at=_utcnow())
        return owner.id, deployment.id


def test_caelus_reports_the_same_read(cli_runner):
    runner, cli_app = cli_runner
    owner_id, deployment_id = _seed_for_cli(owner_email="cli-owner@example.com")

    result = runner.invoke(
        cli_app,
        ["--as-user", "cli-owner@example.com", "get-deployment-database",
         str(owner_id), str(deployment_id)],
    )

    assert result.exit_code == 0, result.output
    assert PASSWORD in result.output
    assert "password_withheld: false" in result.output.lower()
    assert POOLER_HOST in result.output
    assert "postgresql://" not in result.output


def test_caelus_withholds_the_password_from_an_operator_who_is_not_the_owner(cli_runner):
    runner, cli_app = cli_runner
    owner_id, deployment_id = _seed_for_cli(owner_email="cli-owner-2@example.com")

    # `cli-test@example.com`, the fixture's operator, is not the owner.
    result = runner.invoke(
        cli_app, ["get-deployment-database", str(owner_id), str(deployment_id)]
    )

    assert result.exit_code == 0, result.output
    assert PASSWORD not in result.output
    assert "password_withheld: true" in result.output.lower()


def test_caelus_reports_no_database_without_a_traceback(cli_runner):
    from app.db import session_scope

    runner, cli_app = cli_runner
    with session_scope() as session:
        owner = UserORM(email="cli-owner-3@example.com")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        deployment = _deployment(session, user_id=owner.id, enabled=False)
        owner_id, deployment_id = owner.id, deployment.id

    result = runner.invoke(
        cli_app, ["get-deployment-database", str(owner_id), str(deployment_id)]
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
