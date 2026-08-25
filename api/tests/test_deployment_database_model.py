"""The `deployment_database` table.

Covers the two properties the design leans on that no code enforces: the
row's *absence* is what "not provisioned" means, and the row has no
soft-delete column because it must outlive the deployment's deletion.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    DeploymentDatabaseORM,
    ProductORM,
    ProductTemplateVersionORM,
    UserORM,
)
from app.models.core import _utcnow


@pytest.fixture
def session(test_database, db_session):
    with Session(test_database.engine) as session:
        yield session


@pytest.fixture
def deployment(session):
    token = uuid4().hex[:8]
    user = UserORM(email=f"db-{token}@example.com")
    product = ProductORM(name=f"db-product-{token}", created_at=_utcnow())
    session.add(user)
    session.add(product)
    session.commit()
    template = ProductTemplateVersionORM(
        product_id=product.id, chart_ref="oci://example/chart", chart_version="1.0.0"
    )
    session.add(template)
    session.commit()

    from tests.conftest import make_deployment_with_release

    deployment = make_deployment_with_release(
        session,
        user_id=user.id,
        desired_template_id=template.id,
        hostname=f"{token}.example.test",
        name=f"app-{token}",
        namespace=f"ns-{token}",
    )
    session.commit()
    session.refresh(deployment)
    return deployment


def _provision(session, deployment, **overrides) -> DeploymentDatabaseORM:
    name = "dpl_" + deployment.id.hex
    row = DeploymentDatabaseORM(
        deployment_id=deployment.id,
        db_name=overrides.pop("db_name", name),
        role_name=overrides.pop("role_name", name),
        password_encrypted=overrides.pop("password_encrypted", "gAAAAAB..."),
        key_id=overrides.pop("key_id", "1a2b3c4d"),
        created_at=_utcnow(),
        **overrides,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _lookup(session, deployment) -> DeploymentDatabaseORM | None:
    return session.exec(
        select(DeploymentDatabaseORM).where(
            DeploymentDatabaseORM.deployment_id == deployment.id
        )
    ).one_or_none()


def test_absence_of_a_row_is_what_not_provisioned_means(session, deployment):
    """There is no flag to read instead: a deployment with no row has no
    database, and nothing on `deployment` itself says so."""
    assert _lookup(session, deployment) is None
    assert not hasattr(deployment, "database_provisioned")

    row = _provision(session, deployment)
    assert _lookup(session, deployment) is row
    assert row.quota_state == "ok"  # server default, not a Python one
    assert row.purge_after is None
    assert row.size_bytes is None and row.measured_at is None


def test_the_table_has_no_deleted_at(test_database):
    """A soft-delete column would invent a third state between provisioned and
    not provisioned -- and this row already outlives the deployment's own
    deletion, since `purge_after` is recorded on it."""
    columns = {c["name"] for c in inspect(test_database.engine).get_columns("deployment_database")}
    assert "deleted_at" not in columns
    assert "purge_after" in columns


def test_one_database_per_deployment(session, deployment):
    """The unique constraint is what makes "the row" singular: a second
    provision must update the first, never accumulate rows the purge tick
    would then have to disambiguate."""
    _provision(session, deployment)
    with pytest.raises(IntegrityError):
        _provision(session, deployment, db_name="dpl_other", role_name="dpl_other")
    session.rollback()


def test_the_row_survives_a_soft_deleted_deployment(session, deployment):
    """The delete reconcile records a deadline and drops nothing. The row is
    the only record that a database is still out there to purge."""
    row = _provision(session, deployment)
    row.purge_after = _utcnow() + timedelta(days=7)
    deployment.deleted_at = _utcnow()
    deployment.status = "deleted"
    session.add_all([row, deployment])
    session.commit()

    survivor = _lookup(session, deployment)
    assert survivor is not None
    assert survivor.purge_after is not None
    assert survivor.db_name == "dpl_" + deployment.id.hex


def test_purge_index_covers_only_rows_awaiting_a_purge(session):
    """Partial by design: a deployment that was never deleted must not sit in
    the index the purge tick scans."""
    predicate = session.exec(
        text(
            "select indexdef from pg_indexes "
            "where indexname = 'ix_deployment_database_purge_after'"
        )
    ).one()[0]
    assert "WHERE (purge_after IS NOT NULL)" in predicate


def test_names_are_the_deployment_uuid_without_hyphens(session, deployment):
    """D2: one string identifies the tenant in pg_database, pg_roles,
    pg_stat_activity and here -- and it must need no quoting in SQL."""
    row = _provision(session, deployment)
    assert row.db_name == row.role_name
    assert "-" not in row.db_name
    assert len(row.db_name.encode()) <= 63
