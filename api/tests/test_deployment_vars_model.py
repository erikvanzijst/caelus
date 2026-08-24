"""The `deployment_var` table, on both backends the project supports.

Run against SQLite always, and against Postgres when
``POSTGRES_TEST_DATABASE_URL`` is set -- because the two things asserted here
are exactly the ones a single-backend suite gets wrong:

  * the tombstone check constraint, which SQLite *does* enforce (unlike
    foreign keys, see `test_deployment_vars_postgres.py`), and
  * head resolution, which the design writes as Postgres `DISTINCT ON` and
    SQLite has no such thing. The portable spelling below is what
    `app/services/vars.py` will own; the last test pins it against the
    design's own query on the backend that can run both.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session

from app.db import init_db
from app.models import (
    DeploymentVarORM,
    ProductORM,
    ProductTemplateVersionORM,
    UserORM,
)
from app.models.core import _utcnow

PG_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

# The newest row per key, tombstones excluded. Spelled portably: SQLite has no
# `DISTINCT ON`, and a head query that only runs in production is a head query
# nothing tests.
HEAD_SQL = """
SELECT v.key, v.value_encrypted, v.sensitive
  FROM deployment_var v
 WHERE v.deployment_id = :deployment_id
   AND v.id = (SELECT MAX(v2.id)
                 FROM deployment_var v2
                WHERE v2.deployment_id = v.deployment_id
                  AND v2.key = v.key)
   AND v.value_encrypted IS NOT NULL
 ORDER BY v.key
"""

# The design's own formulation (D4), for the parity check.
DISTINCT_ON_SQL = """
SELECT key, value_encrypted, sensitive
  FROM (SELECT DISTINCT ON (key) *
          FROM deployment_var
         WHERE deployment_id = :deployment_id
         ORDER BY key, id DESC) head
 WHERE value_encrypted IS NOT NULL
 ORDER BY key
"""


def _engine(backend: str):
    if backend == "sqlite":
        return create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(PG_TEST_DATABASE_URL)


BACKENDS = ["sqlite"] + (["postgres"] if PG_TEST_DATABASE_URL else [])


@pytest.fixture(params=BACKENDS)
def backend(request) -> str:
    return request.param


@pytest.fixture
def session(backend):
    engine = _engine(backend)
    init_db(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def fixtures(session):
    """A user and a deployment to hang vars off, unique per test."""
    token = uuid4().hex[:8]
    user = UserORM(email=f"vars-{token}@example.com")
    product = ProductORM(name=f"vars-product-{token}", created_at=_utcnow())
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
    return {"user": user, "deployment": deployment, "template": template}


def _set(session, fixtures, key: str, value: str | None, *, sensitive: bool = False):
    row = DeploymentVarORM(
        deployment_id=fixtures["deployment"].id,
        key=key,
        value_encrypted=value,
        key_id=None if value is None else "1a2b3c4d",
        sensitive=sensitive,
        created_by=fixtures["user"].id,
    )
    session.add(row)
    session.commit()
    return row


def _head(session, fixtures, sql: str = HEAD_SQL):
    rows = session.exec(
        text(sql).bindparams(deployment_id=fixtures["deployment"].id)
    ).all()
    return [(r[0], r[1]) for r in rows]


# ── The tombstone check constraint ────────────────────────────────────────


def test_a_value_without_a_key_id_is_rejected(session, fixtures):
    """Ciphertext nothing knows how to read is not a state worth having."""
    session.add(
        DeploymentVarORM(
            deployment_id=fixtures["deployment"].id,
            key="TOKEN",
            value_encrypted="gAAAA-ciphertext",
            key_id=None,
            created_by=fixtures["user"].id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_a_key_id_without_a_value_is_rejected(session, fixtures):
    """A tombstone is the absence of a value, so it names no key."""
    session.add(
        DeploymentVarORM(
            deployment_id=fixtures["deployment"].id,
            key="TOKEN",
            value_encrypted=None,
            key_id="1a2b3c4d",
            created_by=fixtures["user"].id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_a_tombstone_and_a_complete_row_are_both_accepted(session, fixtures):
    _set(session, fixtures, "TOKEN", "ciphertext")
    _set(session, fixtures, "TOKEN", None)


# ── Head resolution ───────────────────────────────────────────────────────


def test_head_is_the_newest_row_per_key(session, fixtures):
    _set(session, fixtures, "LOG_LEVEL", "info")
    _set(session, fixtures, "LOG_LEVEL", "warn")
    _set(session, fixtures, "LOG_LEVEL", "debug")
    _set(session, fixtures, "PORT_OFFSET", "1")
    assert _head(session, fixtures) == [("LOG_LEVEL", "debug"), ("PORT_OFFSET", "1")]


def test_head_excludes_a_key_whose_newest_row_is_a_tombstone(session, fixtures):
    _set(session, fixtures, "LOG_LEVEL", "info")
    _set(session, fixtures, "KEEP", "yes")
    _set(session, fixtures, "LOG_LEVEL", None)
    assert _head(session, fixtures) == [("KEEP", "yes")]


def test_a_re_created_key_is_back_in_head_with_the_tombstone_kept(session, fixtures):
    _set(session, fixtures, "LOG_LEVEL", "info")
    _set(session, fixtures, "LOG_LEVEL", None)
    _set(session, fixtures, "LOG_LEVEL", "trace")
    assert _head(session, fixtures) == [("LOG_LEVEL", "trace")]
    # History is intact: three rows, the tombstone still between the live ones.
    rows = session.exec(
        text(
            "SELECT value_encrypted FROM deployment_var "
            "WHERE deployment_id = :deployment_id ORDER BY id"
        ).bindparams(deployment_id=fixtures["deployment"].id)
    ).all()
    assert [r[0] for r in rows] == ["info", None, "trace"]


def test_head_is_scoped_to_its_own_deployment(session, fixtures, backend):
    _set(session, fixtures, "LOG_LEVEL", "debug")
    other = DeploymentVarORM(
        deployment_id=uuid4() if backend == "sqlite" else fixtures["deployment"].id,
        key="LOG_LEVEL",
        value_encrypted="other",
        key_id="1a2b3c4d",
        created_by=fixtures["user"].id,
    )
    if backend == "sqlite":
        # Postgres would reject the dangling deployment id, and building a
        # second deployment says nothing SQLite cannot already show here.
        session.add(other)
        session.commit()
    assert _head(session, fixtures) == [("LOG_LEVEL", "debug")]


@pytest.mark.skipif(
    not PG_TEST_DATABASE_URL, reason="POSTGRES_TEST_DATABASE_URL is not set"
)
def test_distinct_on_and_the_portable_head_query_agree(session, fixtures, backend):
    """The design writes head as `DISTINCT ON`; only Postgres can run both."""
    if backend != "postgres":
        pytest.skip("DISTINCT ON is Postgres-only")
    _set(session, fixtures, "LOG_LEVEL", "info")
    _set(session, fixtures, "LOG_LEVEL", "debug")
    _set(session, fixtures, "GONE", "value")
    _set(session, fixtures, "GONE", None)
    _set(session, fixtures, "KEEP", "yes", sensitive=True)
    assert _head(session, fixtures) == _head(session, fixtures, DISTINCT_ON_SQL)
    assert _head(session, fixtures) == [("KEEP", "yes"), ("LOG_LEVEL", "debug")]
