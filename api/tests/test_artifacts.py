"""Artifact upload slot tests.

Slot minting is signed by a **real** boto3 client pointed at a dummy endpoint:
`generate_presigned_post` is pure local signing with no network call, so these
assert against the genuine policy document rather than a fake's idea of one.
Only `head_object` — an actual round trip — is faked.
"""

import base64
import json

import boto3
import pytest
from botocore.exceptions import ClientError
from sqlalchemy import inspect, text

from app.config import CaelusSettings
from app.services import artifacts as artifact_service
from app.services.errors import CaelusException, ValidationException
from tests.conftest import (  # noqa: F401
    AUTH_HEADER,
    OTHER_AUTH_HEADER,
    OTHER_EMAIL,
    USER_AUTH_HEADER,
    USER_EMAIL,
    client,
    create_user,
    db_session,
)

BUCKET = "test-bucket"
ENDPOINT = "https://blob.example.invalid"

# Bound before any fixture replaces the module attribute, so the configuration
# test can still reach the genuine lru_cache-wrapped factory.
REAL_GET_S3_CLIENT = artifact_service.get_s3_client


@pytest.fixture
def s3_settings():
    return CaelusSettings(
        _env_file=None,
        s3_endpoint_url=ENDPOINT,
        s3_region="garage",
        s3_bucket=BUCKET,
        s3_access_key_id="GKtest",
        s3_secret_access_key="secret",
    )


@pytest.fixture(autouse=True)
def _signing_client(monkeypatch, s3_settings):
    """Point the service at a real, offline-signing S3 client."""
    signer = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name=s3_settings.s3_region,
        aws_access_key_id=s3_settings.s3_access_key_id,
        aws_secret_access_key=s3_settings.s3_secret_access_key,
    )
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: signer)
    monkeypatch.setattr(artifact_service, "get_settings", lambda: s3_settings)
    return signer


def _policy(slot) -> dict:
    """The decoded policy document the object store will enforce."""
    return json.loads(base64.b64decode(slot["fields"]["policy"]))


def _condition(policy: dict, name: str):
    """Find a list-form condition such as ["content-length-range", 1, N]."""
    for cond in policy["conditions"]:
        if isinstance(cond, list) and cond[0] == name:
            return cond
    return None


def _row_counts(session) -> dict[str, int]:
    insp = inspect(session.get_bind())
    return {
        table: session.exec(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()  # type: ignore[attr-defined]
        for table in insp.get_table_names()
    }


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_authenticated_caller_receives_an_upload_slot(client, s3_settings):
    resp = client.post("/api/artifacts", headers=AUTH_HEADER)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert artifact_service.ARTIFACT_ID_RE.match(body["artifact_id"])
    assert body["url"].startswith(ENDPOINT)
    assert body["max_bytes"] == s3_settings.artifact_max_bytes
    assert body["expires_in"] == s3_settings.s3_presigned_url_expiry_seconds
    # The fields a client must post verbatim for the policy to validate.
    assert {"key", "policy", "x-amz-signature", "x-amz-credential"} <= set(body["fields"])


def test_anonymous_caller_is_refused_and_gets_no_slot(client):
    # The shared fixture authenticates every request by default; strip that.
    del client.headers["X-Auth-Request-Email"]

    resp = client.post("/api/artifacts")

    assert resp.status_code == 404
    assert "artifact_id" not in resp.json()


def test_key_encodes_the_authenticated_caller(client):
    user = create_user(client, USER_EMAIL)

    body = client.post("/api/artifacts", headers=USER_AUTH_HEADER).json()

    assert body["fields"]["key"] == f"artifacts/{user['id']}/{body['artifact_id']}.tgz"


def test_two_callers_get_slots_under_their_own_prefixes(client):
    one = create_user(client, USER_EMAIL)
    two = create_user(client, OTHER_EMAIL)

    first = client.post("/api/artifacts", headers=USER_AUTH_HEADER).json()
    second = client.post("/api/artifacts", headers=OTHER_AUTH_HEADER).json()

    assert first["fields"]["key"].startswith(f"artifacts/{one['id']}/")
    assert second["fields"]["key"].startswith(f"artifacts/{two['id']}/")
    assert first["artifact_id"] != second["artifact_id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"key": "artifacts/99/pwned.tgz"},
        {"path": "../../etc/passwd"},
        {"url": "https://evil.example.com/upload"},
        {"artifact_id": "0" * 32},
        {"user_id": 99},
        {"bucket": "some-other-bucket"},
    ],
)
def test_caller_supplied_location_does_not_influence_the_slot(client, payload):
    """The endpoint takes no body at all, so there is nothing to subvert."""
    user = create_user(client, USER_EMAIL)

    resp = client.post("/api/artifacts", headers=USER_AUTH_HEADER, json=payload)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["fields"]["key"] == f"artifacts/{user['id']}/{body['artifact_id']}.tgz"
    assert body["artifact_id"] != "0" * 32
    assert BUCKET in body["url"] or body["url"].startswith(ENDPOINT)


def test_minting_a_slot_creates_no_persistent_record(client, db_session):
    create_user(client, USER_EMAIL)
    before = _row_counts(db_session)

    for _ in range(3):
        assert client.post("/api/artifacts", headers=USER_AUTH_HEADER).status_code == 201

    assert _row_counts(db_session) == before
    assert before["build"] == 0


def test_each_call_mints_a_fresh_artifact_id(client):
    create_user(client, USER_EMAIL)

    ids = {
        client.post("/api/artifacts", headers=USER_AUTH_HEADER).json()["artifact_id"]
        for _ in range(5)
    }

    assert len(ids) == 5


# ---------------------------------------------------------------------------
# The policy the object store will enforce
# ---------------------------------------------------------------------------


def test_policy_caps_the_upload_size(client, s3_settings):
    slot = client.post("/api/artifacts", headers=AUTH_HEADER).json()

    condition = _condition(_policy(slot), "content-length-range")

    assert condition == ["content-length-range", 1, s3_settings.artifact_max_bytes]


def test_policy_pins_the_key_exactly_rather_than_by_prefix(client):
    """An exact match is what makes "upload to a different key is rejected"
    true; a `starts-with` on key would widen the grant to the whole prefix."""
    slot = client.post("/api/artifacts", headers=AUTH_HEADER).json()
    policy = _policy(slot)

    assert {"key": slot["fields"]["key"]} in policy["conditions"]
    assert _condition(policy, "starts-with") is None


def test_policy_carries_the_configured_expiry(client, s3_settings, monkeypatch):
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    slot = client.post("/api/artifacts", headers=AUTH_HEADER).json()

    expiration = datetime.strptime(
        _policy(slot)["expiration"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=UTC)
    ttl = (expiration - before).total_seconds()

    assert 0 < ttl <= s3_settings.s3_presigned_url_expiry_seconds + 5


# ---------------------------------------------------------------------------
# Key derivation and artifact id validation
# ---------------------------------------------------------------------------


def test_artifact_key_is_composed_from_the_owner_and_the_id():
    artifact_id = "a" * 32

    assert artifact_service.artifact_key(7, artifact_id) == f"artifacts/7/{artifact_id}.tgz"


@pytest.mark.parametrize(
    "bad",
    [
        "../7/" + "a" * 26,
        "..%2f7%2f" + "a" * 23,
        "a" * 32 + "/../../7/x",
        "artifacts/7/" + "a" * 20,
        "A" * 32,
        "a" * 31,
        "a" * 33,
        "",
        "a" * 30 + "zz",
    ],
)
def test_a_malformed_artifact_id_is_rejected_rather_than_composed(bad):
    """Traversal never reaches key composition: it is not a well-formed id."""
    with pytest.raises(ValidationException):
        artifact_service.artifact_key(7, bad)


def test_minted_ids_are_always_well_formed(s3_settings):
    for _ in range(20):
        slot = artifact_service.mint_upload_slot(7, settings=s3_settings)
        assert artifact_service.validate_artifact_id(slot.artifact_id)


# ---------------------------------------------------------------------------
# Existence check (used by build creation)
# ---------------------------------------------------------------------------


class _FakeS3:
    def __init__(self, *, present: set[str] | None = None, error: ClientError | None = None):
        self.present = present or set()
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def head_object(self, Bucket: str, Key: str):  # noqa: N803 — boto3's own casing
        self.calls.append((Bucket, Key))
        if self.error is not None:
            raise self.error
        if Key not in self.present:
            raise _client_error(404, "404")
        return {"ContentLength": 123}


def _client_error(status: int, code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "HeadObject",
    )


def test_artifact_exists_looks_under_the_owners_derived_key(monkeypatch, s3_settings):
    artifact_id = "b" * 32
    fake = _FakeS3(present={f"artifacts/5/{artifact_id}.tgz"})
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: fake)

    assert artifact_service.artifact_exists(5, artifact_id, settings=s3_settings) is True
    assert fake.calls == [(BUCKET, f"artifacts/5/{artifact_id}.tgz")]


def test_another_users_artifact_is_simply_absent(monkeypatch, s3_settings):
    """No ownership check to get wrong: the key another user's id builds is
    not the key the caller's id builds."""
    artifact_id = "c" * 32
    fake = _FakeS3(present={f"artifacts/5/{artifact_id}.tgz"})
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: fake)

    assert artifact_service.artifact_exists(6, artifact_id, settings=s3_settings) is False


@pytest.mark.parametrize("status,code", [(404, "404"), (403, "AccessDenied")])
def test_a_missing_or_hidden_artifact_reads_as_absent(monkeypatch, s3_settings, status, code):
    fake = _FakeS3(error=_client_error(status, code))
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: fake)

    assert artifact_service.artifact_exists(5, "d" * 32, settings=s3_settings) is False


def test_an_object_store_outage_is_not_reported_as_a_missing_artifact(monkeypatch, s3_settings):
    """A 500 must not be laundered into "you never uploaded it"."""
    fake = _FakeS3(error=_client_error(500, "InternalError"))
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: fake)

    with pytest.raises(ClientError):
        artifact_service.artifact_exists(5, "e" * 32, settings=s3_settings)


def test_existence_check_rejects_a_malformed_artifact_id(monkeypatch, s3_settings):
    fake = _FakeS3()
    monkeypatch.setattr(artifact_service, "get_s3_client", lambda: fake)

    with pytest.raises(ValidationException):
        artifact_service.artifact_exists(5, "../6/" + "a" * 27, settings=s3_settings)
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_an_unconfigured_object_store_fails_loudly(monkeypatch):
    """A blank s3_* config must not silently presign against nothing."""
    monkeypatch.setattr(
        artifact_service, "get_settings", lambda: CaelusSettings(_env_file=None)
    )
    # REAL_GET_S3_CLIENT is bound at import time, before the autouse fixture
    # swaps the module attribute for an offline signer.
    REAL_GET_S3_CLIENT.cache_clear()
    try:
        with pytest.raises(CaelusException, match="not configured"):
            REAL_GET_S3_CLIENT()
    finally:
        REAL_GET_S3_CLIENT.cache_clear()
