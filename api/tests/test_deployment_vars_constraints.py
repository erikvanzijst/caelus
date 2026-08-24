"""Referential behavior of the var tables.

A missing `ON DELETE CASCADE` here would only surface when someone deletes a
deployment in production, so the cascade is asserted directly against the
constraints the migration chain creates.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError
from sqlmodel import Session, select

from app.models import (
    DeploymentReleaseORM,
    DeploymentVarORM,
    ProductORM,
    ProductTemplateVersionORM,
    ReleaseVarORM,
    UserORM,
)
from app.models.core import _utcnow


@pytest.fixture
def engine(test_database, db_session):
    """The shared test database: already migrated, and empty for this test.

    `db_session` is requested purely for its reset -- this file talks to the
    database through its own short-lived sessions.
    """
    return test_database.engine


@pytest.fixture
def scenario(engine):
    """A deployment with a release, one live var and one tombstone, and a
    snapshot binding the live var to the release."""
    from tests.conftest import make_deployment_with_release

    token = uuid4().hex[:8]
    with Session(engine) as session:
        user = UserORM(email=f"vars-pg-{token}@example.com")
        product = ProductORM(name=f"vars-pg-product-{token}", created_at=_utcnow())
        session.add(user)
        session.add(product)
        session.commit()
        template = ProductTemplateVersionORM(
            product_id=product.id, chart_ref="oci://example/chart", chart_version="1.0.0"
        )
        session.add(template)
        session.commit()

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

        live = DeploymentVarORM(
            deployment_id=deployment.id,
            key="LOG_LEVEL",
            value_encrypted="ciphertext",
            key_id="1a2b3c4d",
            created_by=user.id,
        )
        tombstone = DeploymentVarORM(
            deployment_id=deployment.id, key="GONE", created_by=user.id
        )
        session.add(live)
        session.add(tombstone)
        session.commit()
        session.refresh(live)

        session.add(
            ReleaseVarORM(release_id=deployment.desired_release_id, var_id=live.id)
        )
        session.commit()

        yield {
            "deployment_id": deployment.id,
            "release_id": deployment.desired_release_id,
            "var_id": live.id,
            "user_id": user.id,
        }


def _counts(engine, scenario):
    with Session(engine) as session:
        vars_ = session.exec(
            select(DeploymentVarORM).where(
                DeploymentVarORM.deployment_id == scenario["deployment_id"]
            )
        ).all()
        bindings = session.exec(
            select(ReleaseVarORM).where(ReleaseVarORM.release_id == scenario["release_id"])
        ).all()
    return len(vars_), len(bindings)


def test_deleting_the_deployment_removes_its_vars_and_their_bindings(engine, scenario):
    """E12: the plaintext was never stored, and the ciphertext goes with the rows.

    It also has to *succeed*: a missing cascade would not orphan the rows, it
    would fail the delete on a foreign key.
    """
    assert _counts(engine, scenario) == (2, 1)
    with Session(engine) as session:
        session.exec(
            text("DELETE FROM deployment WHERE id = :id").bindparams(
                id=scenario["deployment_id"]
            )
        )
        session.commit()
    assert _counts(engine, scenario) == (0, 0)


def test_deleting_a_release_removes_its_bindings_but_not_the_vars(engine, scenario):
    """A snapshot belongs to its release; the history outlives it.

    Deleted through a *second* release, because the one the deployment points
    at cannot go on its own -- `desired_release_id` is NOT NULL.
    """
    second_id = uuid4()
    with Session(engine) as session:
        session.add(
            DeploymentReleaseORM(
                id=second_id,
                number=2,
                deployment_id=scenario["deployment_id"],
                template_id=session.exec(
                    text("SELECT desired_template_id FROM deployment WHERE id = :id")
                    .bindparams(id=scenario["deployment_id"])
                ).one()[0],
            )
        )
        session.commit()
        session.add(ReleaseVarORM(release_id=second_id, var_id=scenario["var_id"]))
        session.commit()

        session.exec(
            text("DELETE FROM deployment_release WHERE id = :id").bindparams(id=second_id)
        )
        session.commit()

        assert session.exec(
            select(ReleaseVarORM).where(ReleaseVarORM.release_id == second_id)
        ).all() == []
    # The var row, and the first release's binding to it, are untouched.
    assert _counts(engine, scenario) == (2, 1)


def test_a_var_row_cannot_choose_its_own_id(engine, scenario):
    """`id` is IDENTITY ALWAYS: head resolution and the release snapshot both
    order by it, so it is the record of what was written after what."""
    with Session(engine) as session:
        with pytest.raises(DatabaseError):
            session.exec(
                text(
                    "INSERT INTO deployment_var "
                    "(id, deployment_id, key, created_by, created_at) "
                    "VALUES (1, :did, 'PINNED', :uid, now())"
                ).bindparams(did=scenario["deployment_id"], uid=scenario["user_id"])
            )
            session.commit()
        session.rollback()


def test_a_release_binds_a_var_at_most_once(engine, scenario):
    from sqlalchemy.exc import IntegrityError

    with Session(engine) as session:
        session.add(
            ReleaseVarORM(release_id=scenario["release_id"], var_id=scenario["var_id"])
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
