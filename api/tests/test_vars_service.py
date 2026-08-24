"""`app.services.vars`: head, writes, snapshots and `pending`.

The edge cases from the design's own list are named in the tests that cover
them (E1-E6, E9, E10), so a change that breaks one is reported in the
vocabulary the design uses.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlmodel import select

from app.models import (
    DeploymentReleaseORM,
    DeploymentVarORM,
    ProductORM,
    ProductTemplateVersionORM,
    UserORM,
    VarWrite,
)
from app.models.core import _utcnow
from app.services import vars as vars_service
from app.services import var_crypto
from app.services.errors import ValidationException
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_PROVISIONING,
    DEPLOYMENT_STATUS_READY,
)
from tests.conftest import db_session, make_deployment_with_release  # noqa: F401

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

OPEN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "x-caelus-vars-additional": True,
    "properties": {"hostname": {"type": "string"}},
}


def _make_env(db_session, schema, *, prefix):
    """A deployment whose template declares `schema`, plus two users."""
    owner = UserORM(email=f"{prefix}-owner@example.com")
    other = UserORM(email=f"{prefix}-other@example.com")
    product = ProductORM(name=f"{prefix}prod", created_at=_utcnow())
    db_session.add_all([owner, other, product])
    db_session.commit()
    template = ProductTemplateVersionORM(
        product_id=product.id,
        chart_ref="oci://example/chart",
        chart_version="1.0.0",
        values_schema_json=schema,
    )
    db_session.add(template)
    db_session.commit()

    deployment = make_deployment_with_release(
        db_session,
        user_id=owner.id,
        desired_template_id=template.id,
        hostname=f"{prefix}.example.test",
        name=f"{prefix}-app",
        namespace=f"ns-{prefix}",
        status=DEPLOYMENT_STATUS_READY,
    )
    db_session.commit()
    db_session.refresh(deployment)
    return {
        "session": db_session,
        "owner": owner,
        "other": other,
        "product": product,
        "template": template,
        "deployment": deployment,
    }


@pytest.fixture
def env(db_session):
    """A deployment whose schema declares its runtime properties."""
    return _make_env(db_session, SCHEMA, prefix="vars")


@pytest.fixture
def open_env(db_session):
    """A `custom`-shaped deployment: closed chart half, open vars half.

    The only shape in which a caller controls sensitivity at all, so it is
    where flipping a var's sensitivity can be exercised.
    """
    return _make_env(db_session, OPEN_SCHEMA, prefix="open")


def _write(env, entries, *, actor=None, replace=False):
    vars_service.write_vars(
        env["session"],
        deployment=env["deployment"],
        actor=actor or env["owner"],
        entries=entries,
        replace=replace,
    )
    env["session"].commit()


def _rows(env, key=None):
    query = select(DeploymentVarORM).where(
        DeploymentVarORM.deployment_id == env["deployment"].id
    )
    if key is not None:
        query = query.where(DeploymentVarORM.key == key)
    return env["session"].exec(query.order_by(DeploymentVarORM.id)).all()


def _head(env):
    return vars_service.head(env["session"], env["deployment"].id)


def _plaintext(env, key):
    return var_crypto.decrypt(_head(env)[key].value_encrypted, _head(env)[key].key_id)


# ── Storage basics ────────────────────────────────────────────────────────


def test_a_value_is_never_stored_in_plaintext(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    row = _rows(env)[0]
    assert row.value_encrypted is not None
    assert "debug" not in row.value_encrypted
    assert row.key_id == var_crypto.current_key_id()
    assert _plaintext(env, "LOG_LEVEL") == "debug"


def test_a_non_sensitive_value_is_encrypted_too(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert _rows(env)[0].sensitive is False
    assert _rows(env)[0].value_encrypted is not None


def test_head_is_the_newest_row_per_key(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    _write(env, {"LOG_LEVEL": VarWrite(value="warn")})
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert len(_rows(env, "LOG_LEVEL")) == 3
    assert _plaintext(env, "LOG_LEVEL") == "debug"


# ── The edge cases the design enumerates ──────────────────────────────────


def test_e1_a_var_on_a_deployment_that_has_never_rolled_out(env):
    """E1: legal; head is non-empty and `pending` is true."""
    assert env["deployment"].applied_release_id is None
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert set(_head(env)) == {"LOG_LEVEL"}
    assert vars_service.pending(env["session"], env["deployment"]) is True


def test_e2_deleting_a_key_that_does_not_exist(env):
    """E2: an idempotent no-op -- no tombstone over nothing."""
    vars_service.delete_var(
        env["session"], deployment=env["deployment"], actor=env["owner"], key="LOG_LEVEL"
    )
    env["session"].commit()
    assert _rows(env) == []

    _write(env, {"LOG_LEVEL": VarWrite(value=None)})
    assert _rows(env) == []


def test_e3_setting_a_var_to_the_value_it_already_has(env):
    """E3: writes no row. Without the diff, every deploy appends a full copy."""
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert len(_rows(env)) == 1


def test_e3_extends_to_a_whole_unchanged_configuration(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="debug"), "ADMIN_TOKEN": VarWrite(value="s3cret")})
    before = len(_rows(env))
    _write(env, {"LOG_LEVEL": VarWrite(value="debug"), "ADMIN_TOKEN": VarWrite(value="s3cret")})
    assert len(_rows(env)) == before


def test_e4_a_key_whose_newest_row_is_a_tombstone(env):
    """E4: out of head, out of every read, never bound to a release."""
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    _write(env, {"LOG_LEVEL": VarWrite(value=None)})

    assert _head(env) == {}
    assert vars_service.read_vars(env["session"], env["deployment"]).vars == {}
    # History is intact.
    assert [row.value_encrypted is None for row in _rows(env)] == [False, True]

    release_id = env["deployment"].desired_release_id
    vars_service.snapshot_release(
        env["session"], release_id=release_id, deployment_id=env["deployment"].id
    )
    env["session"].commit()
    assert vars_service.snapshot(env["session"], release_id) == []


def test_e5_re_creating_a_deleted_key(env):
    """E5: an ordinary insert; the tombstone stays between the two live rows."""
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    _write(env, {"LOG_LEVEL": VarWrite(value=None)})
    _write(env, {"LOG_LEVEL": VarWrite(value="trace")})

    assert _plaintext(env, "LOG_LEVEL") == "trace"
    rows = _rows(env)
    assert [row.value_encrypted is None for row in rows] == [False, True, False]


def test_e6_flipping_a_var_to_sensitive(open_env):
    """E6: allowed, and it writes a new row with the same plaintext.

    Only reachable where the caller owns sensitivity: where the schema
    declares the property, the schema decides and a contradiction is refused.
    """
    env = open_env
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    _write(env, {"LOG_LEVEL": VarWrite(value="debug", sensitive=True)})

    rows = _rows(env)
    assert [row.sensitive for row in rows] == [False, True]
    assert _plaintext(env, "LOG_LEVEL") == "debug"
    # Re-encrypted, not copied: Fernet's IV is random.
    assert rows[0].value_encrypted != rows[1].value_encrypted


def test_e6_the_reverse_flip_requires_a_new_value(open_env):
    """E6: exposing a value someone marked sensitive is worse than a retype."""
    env = open_env
    _write(env, {"LOG_LEVEL": VarWrite(value="debug", sensitive=True)})
    with pytest.raises(ValidationException) as exc:
        _write(env, {"LOG_LEVEL": VarWrite(sensitive=False)})
    assert "LOG_LEVEL" in str(exc.value)
    assert _head(env)["LOG_LEVEL"].sensitive is True

    _write(env, {"LOG_LEVEL": VarWrite(value="debug", sensitive=False)})
    assert _head(env)["LOG_LEVEL"].sensitive is False


def test_e9_a_var_write_during_a_rollout_is_staged_for_the_next_release(env):
    """E9: a staged write while a rollout is in flight is legal.

    Ordering is the deployment row lock's job, which SQLite cannot exercise;
    what is asserted here is the consequence -- the write lands, the in-flight
    release's snapshot does not change, and the next release picks it up.
    """
    session = env["session"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    first = env["deployment"].desired_release_id
    vars_service.snapshot_release(session, release_id=first, deployment_id=env["deployment"].id)
    session.commit()

    env["deployment"].status = DEPLOYMENT_STATUS_PROVISIONING
    session.add(env["deployment"])
    session.commit()

    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})

    assert len(vars_service.snapshot(session, first)) == 1
    assert var_crypto.decrypt(
        vars_service.snapshot(session, first)[0].value_encrypted,
        vars_service.snapshot(session, first)[0].key_id,
    ) == "info"

    second = uuid4()
    session.add(
        DeploymentReleaseORM(
            id=second,
            number=2,
            deployment_id=env["deployment"].id,
            template_id=env["template"].id,
        )
    )
    session.commit()
    vars_service.snapshot_release(session, release_id=second, deployment_id=env["deployment"].id)
    session.commit()
    assert vars_service.snapshot(session, second)[0].id == _head(env)["LOG_LEVEL"].id


def test_e10_two_writers_of_one_key(env):
    """E10: last writer wins on `id`; both are visible in history."""
    _write(env, {"LOG_LEVEL": VarWrite(value="info")}, actor=env["owner"])
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")}, actor=env["other"])

    rows = _rows(env, "LOG_LEVEL")
    assert [row.created_by for row in rows] == [env["owner"].id, env["other"].id]
    assert _head(env)["LOG_LEVEL"].id == rows[-1].id
    assert _plaintext(env, "LOG_LEVEL") == "debug"


# ── Merge, replace, and the three states of `value` ───────────────────────


def test_patch_leaves_absent_keys_alone(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="info"), "ADMIN_TOKEN": VarWrite(value="s3cret")})
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert set(_head(env)) == {"LOG_LEVEL", "ADMIN_TOKEN"}


def test_put_deletes_absent_keys(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="info"), "ADMIN_TOKEN": VarWrite(value="s3cret")})
    _write(env, {"LOG_LEVEL": VarWrite(value="info")}, replace=True)
    assert set(_head(env)) == {"LOG_LEVEL"}


def test_an_absent_value_leaves_a_var_unchanged(env):
    _write(env, {"ADMIN_TOKEN": VarWrite(value="s3cret")})
    before = _head(env)["ADMIN_TOKEN"].id
    _write(env, {"ADMIN_TOKEN": VarWrite()})
    assert _head(env)["ADMIN_TOKEN"].id == before


def test_an_absent_value_for_an_unknown_key_is_rejected(env):
    with pytest.raises(ValidationException) as exc:
        _write(env, {"LOG_LEVEL": VarWrite()})
    assert "LOG_LEVEL" in str(exc.value)


# ── Sensitivity resolution ────────────────────────────────────────────────


def test_sensitivity_comes_from_the_schema_when_it_declares_the_property(env):
    _write(env, {"ADMIN_TOKEN": VarWrite(value="s3cret")})
    assert _head(env)["ADMIN_TOKEN"].sensitive is True


def test_contradicting_the_schema_is_rejected(env):
    with pytest.raises(ValidationException) as exc:
        _write(env, {"ADMIN_TOKEN": VarWrite(value="s3cret", sensitive=False)})
    assert "ADMIN_TOKEN" in str(exc.value)
    assert _rows(env) == []


def test_on_an_open_projection_the_caller_decides(open_env):
    env = open_env
    _write(env, {"ANYTHING": VarWrite(value="1")})
    assert _head(env)["ANYTHING"].sensitive is False

    _write(env, {"SECRET": VarWrite(value="s3cret", sensitive=True)})
    assert _head(env)["SECRET"].sensitive is True

    # Silence about an existing sensitive var keeps it sensitive rather than
    # silently exposing it.
    _write(env, {"SECRET": VarWrite(value="rotated")})
    assert _head(env)["SECRET"].sensitive is True


# ── Limits and reserved names ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "key", ["log-level", "1LEVEL", "", "A" * 65, "PORT", "AWS_SECRET_ACCESS_KEY",
            "CAELUS_ANYTHING", "S3_BUCKET", "RAILPACK_CONFIG_FILE", "BUCKET_NAME"]
)
def test_an_illegal_or_reserved_key_is_rejected(env, key):
    with pytest.raises(ValidationException):
        _write(env, {key: VarWrite(value="1")})
    assert _rows(env) == []


def test_an_oversized_value_is_rejected_without_quoting_it(env):
    value = "x" * (vars_service.MAX_VAR_VALUE_BYTES + 1)
    with pytest.raises(ValidationException) as exc:
        _write(env, {"LOG_LEVEL": VarWrite(value=value)})
    assert "LOG_LEVEL" in str(exc.value)
    assert value not in str(exc.value)
    assert _rows(env) == []


def test_too_many_vars_are_rejected(monkeypatch, env):
    monkeypatch.setattr(vars_service, "MAX_VARS_PER_DEPLOYMENT", 2)
    with pytest.raises(ValidationException):
        _write(
            env,
            {
                "A": VarWrite(value="1"),
                "B": VarWrite(value="2"),
                "C": VarWrite(value="3"),
            },
        )


def test_total_size_is_bounded_across_the_whole_head(env, monkeypatch):
    monkeypatch.setattr(vars_service, "MAX_VARS_TOTAL_BYTES", 8)
    _write(env, {"LOG_LEVEL": VarWrite(value="12345")})
    with pytest.raises(ValidationException):
        # Under the per-value limit, over the total once head is counted.
        _write(env, {"ADMIN_TOKEN": VarWrite(value="12345")})


def test_a_value_the_schema_rejects_never_reaches_storage(env):
    with pytest.raises(ValidationException) as exc:
        _write(env, {"SIGNUPS_ALLOWED": VarWrite(value="yes")})
    assert str(exc.value) == 'vars.SIGNUPS_ALLOWED: failed constraint "type"'
    assert _rows(env) == []


def test_a_chart_property_cannot_be_written_as_a_var(env):
    with pytest.raises(ValidationException):
        _write(env, {"host": VarWrite(value="example.test")})


# ── Snapshots and pending ─────────────────────────────────────────────────


def test_a_snapshot_freezes_what_the_release_shipped(env):
    session = env["session"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    release_id = env["deployment"].desired_release_id
    vars_service.snapshot_release(
        session, release_id=release_id, deployment_id=env["deployment"].id
    )
    session.commit()

    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    _write(env, {"ADMIN_TOKEN": VarWrite(value="s3cret")})

    frozen = vars_service.snapshot(session, release_id)
    assert [row.key for row in frozen] == ["LOG_LEVEL"]
    assert var_crypto.decrypt(frozen[0].value_encrypted, frozen[0].key_id) == "info"


def test_pending_is_false_once_the_applied_release_carries_head(env):
    session = env["session"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    release_id = env["deployment"].desired_release_id
    vars_service.snapshot_release(
        session, release_id=release_id, deployment_id=env["deployment"].id
    )
    env["deployment"].applied_release_id = release_id
    session.add(env["deployment"])
    session.commit()

    assert vars_service.pending(session, env["deployment"]) is False

    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    assert vars_service.pending(session, env["deployment"]) is True


def test_pending_is_measured_against_the_applied_release_not_the_desired_one(env):
    """After a failed rollout head equals the *failed* release's snapshot, so a
    diff against desired would report nothing pending while the running pod
    carries none of the changes."""
    session = env["session"]
    deployment = env["deployment"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    applied = deployment.desired_release_id
    vars_service.snapshot_release(session, release_id=applied, deployment_id=deployment.id)
    deployment.applied_release_id = applied
    session.add(deployment)
    session.commit()

    # A second release is asked for, carrying a change, and fails.
    _write(env, {"LOG_LEVEL": VarWrite(value="debug")})
    failed = uuid4()
    session.add(
        DeploymentReleaseORM(
            id=failed,
            number=2,
            deployment_id=deployment.id,
            template_id=env["template"].id,
            error="boom",
        )
    )
    session.commit()
    vars_service.snapshot_release(session, release_id=failed, deployment_id=deployment.id)
    deployment.desired_release_id = failed
    session.add(deployment)
    session.commit()

    assert vars_service.pending(session, deployment) is True


def test_rotation_does_not_make_a_deployment_look_pending(env):
    """`pending` compares row identity, and rotation preserves it."""
    session = env["session"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    release_id = env["deployment"].desired_release_id
    vars_service.snapshot_release(
        session, release_id=release_id, deployment_id=env["deployment"].id
    )
    env["deployment"].applied_release_id = release_id
    session.add(env["deployment"])
    session.commit()
    assert vars_service.pending(session, env["deployment"]) is False

    from cryptography.fernet import Fernet
    from app.config import CaelusSettings
    from tests.conftest import TEST_VAR_ENCRYPTION_KEY

    new_key = Fernet.generate_key().decode()
    var_crypto.get_settings = lambda: CaelusSettings(  # type: ignore[assignment]
        var_encryption_keys=[new_key, TEST_VAR_ENCRYPTION_KEY], _env_file=None
    )
    var_crypto.get_keyring.cache_clear()
    assert var_crypto.rotate_vars(session) == 1

    assert vars_service.pending(session, env["deployment"]) is False
    assert _plaintext(env, "LOG_LEVEL") == "info"


def test_a_deleted_var_leaves_an_earlier_snapshot_intact(env):
    session = env["session"]
    _write(env, {"LOG_LEVEL": VarWrite(value="info")})
    release_id = env["deployment"].desired_release_id
    vars_service.snapshot_release(
        session, release_id=release_id, deployment_id=env["deployment"].id
    )
    session.commit()

    _write(env, {"LOG_LEVEL": VarWrite(value=None)})

    assert _head(env) == {}
    assert [row.key for row in vars_service.snapshot(session, release_id)] == ["LOG_LEVEL"]


def test_reads_omit_a_sensitive_value(env):
    _write(env, {"LOG_LEVEL": VarWrite(value="debug"), "ADMIN_TOKEN": VarWrite(value="s3cret")})
    payload = vars_service.read_vars(env["session"], env["deployment"]).model_dump()
    assert payload["vars"]["LOG_LEVEL"]["value"] == "debug"
    assert "value" not in payload["vars"]["ADMIN_TOKEN"]
    assert payload["vars"]["ADMIN_TOKEN"]["sensitive"] is True
