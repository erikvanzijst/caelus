"""Build API tests: creation, authorization, listing, and the log endpoint.

The object store is faked at the `artifacts` service boundary — build creation
only ever asks it "is this artifact there?", so a set of present keys is the
whole fidelity required. Everything else is real: the router, the service, and
the database constraints.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import select

from app.models import BuildCreate, BuildORM
from app.services import artifacts as artifact_service
from app.services import builds as build_service
from app.services.build_constants import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCEEDED,
    BUILD_STATUSES_TERMINAL,
)
from app.services.errors import NotFoundException, ValidationException
from tests.conftest import (  # noqa: F401
    ADMIN_EMAIL,
    AUTH_HEADER,
    OTHER_AUTH_HEADER,
    OTHER_EMAIL,
    USER_AUTH_HEADER,
    USER_EMAIL,
    client,
    create_user,
    db_session,
)

ARTIFACT = "a" * 32
OTHER_ARTIFACT = "b" * 32


def _builds(user_id, *suffix):
    """The builds URL for one account, which is the only way in."""
    return "/".join((f"/api/users/{user_id}/builds", *(str(p) for p in suffix)))


class _FakeStore:
    """Stands in for Garage: a set of object keys that exist."""

    def __init__(self):
        self.keys: set[str] = set()
        self.checked: list[str] = []

    def upload(self, user_id: int, artifact_id: str) -> str:
        self.keys.add(artifact_service.artifact_key(user_id, artifact_id))
        return artifact_id

    def exists(self, user_id: int, artifact_id: str, *, settings=None) -> bool:
        key = artifact_service.artifact_key(user_id, artifact_id)
        self.checked.append(key)
        return key in self.keys


@pytest.fixture
def store(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr(build_service, "artifact_exists", fake.exists)
    return fake


@pytest.fixture
def user(client):
    return create_user(client, USER_EMAIL)


def _create(client, artifact_id, owner, headers=USER_AUTH_HEADER, **kwargs):
    return client.post(
        _builds(owner), json={"artifact_id": artifact_id, **kwargs}, headers=headers
    )


def _seed(session, *, user_id, artifact_id, status=BUILD_STATUS_QUEUED, log=b"", **kwargs):
    build = BuildORM(
        user_id=user_id, artifact_id=artifact_id, status=status, log=log, **kwargs
    )
    session.add(build)
    session.commit()
    session.refresh(build)
    return build


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_build_is_created_from_an_uploaded_artifact(client, store, user):
    store.upload(user["id"], ARTIFACT)

    resp = _create(client, ARTIFACT, user["id"])

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == BUILD_STATUS_QUEUED
    assert body["user_id"] == user["id"]
    assert body["artifact_id"] == ARTIFACT
    assert body["started_at"] is None and body["finished_at"] is None
    assert body["image"] is None
    # The spec asks for the new build's location.
    assert resp.headers["Location"] == f"/api/users/{user['id']}/builds/{body['id']}"


def test_owner_is_the_caller_not_the_request_body(client, store, user):
    """A user_id in the body is refused, not silently honored or dropped."""
    store.upload(user["id"], ARTIFACT)

    resp = _create(client, ARTIFACT, user["id"], user_id=99999)

    assert resp.status_code == 422
    assert "user_id" in resp.text


def test_anonymous_creation_is_refused(client, store, db_session):
    del client.headers["X-Auth-Request-Email"]

    resp = _create(client, ARTIFACT, 1, headers={})

    assert resp.status_code == 404
    assert db_session.exec(select(BuildORM)).all() == []


def test_missing_artifact_is_rejected_with_a_client_error(client, store, user, db_session):
    resp = _create(client, ARTIFACT, user["id"])  # never uploaded

    assert resp.status_code == 400
    assert ARTIFACT in resp.json()["detail"]
    assert db_session.exec(select(BuildORM)).all() == []


def test_another_users_artifact_is_not_reachable(client, store, user):
    """The key is derived from the caller, so someone else's artifact is
    simply absent — there is no ownership check to bypass."""
    other = create_user(client, OTHER_EMAIL)
    store.upload(other["id"], ARTIFACT)

    resp = _create(client, ARTIFACT, user["id"], headers=USER_AUTH_HEADER)

    assert resp.status_code == 400
    assert store.checked == [artifact_service.artifact_key(user["id"], ARTIFACT)]


@pytest.mark.parametrize("bad", ["../7/" + "a" * 26, "A" * 32, "a" * 31, "", "not-hex" * 4])
def test_a_malformed_artifact_id_is_rejected(client, store, user, bad):
    resp = _create(client, bad, user["id"])

    assert resp.status_code == 400
    assert store.checked == []


@pytest.mark.parametrize("in_flight", [BUILD_STATUS_QUEUED, BUILD_STATUS_RUNNING])
def test_retry_while_a_build_is_in_flight_returns_the_existing_build(
    client, store, user, db_session, in_flight
):
    store.upload(user["id"], ARTIFACT)
    first = _create(client, ARTIFACT, user["id"]).json()
    build = db_session.get(BuildORM, UUID(first["id"]))
    build.status = in_flight
    db_session.add(build)
    db_session.commit()

    resp = _create(client, ARTIFACT, user["id"])

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == first["id"]
    assert len(db_session.exec(select(BuildORM)).all()) == 1


def test_a_retry_does_not_re_check_the_object_store(client, store, user):
    """An in-flight build proves the artifact was there; re-checking would
    fail a legitimate retry whose artifact has since expired."""
    store.upload(user["id"], ARTIFACT)
    _create(client, ARTIFACT, user["id"])
    store.keys.clear()
    store.checked.clear()

    resp = _create(client, ARTIFACT, user["id"])

    assert resp.status_code == 200
    assert store.checked == []


@pytest.mark.parametrize("terminal", BUILD_STATUSES_TERMINAL)
def test_rebuild_after_a_terminal_build_creates_a_new_one(
    client, store, user, db_session, terminal
):
    store.upload(user["id"], ARTIFACT)
    first = _create(client, ARTIFACT, user["id"]).json()
    build = db_session.get(BuildORM, UUID(first["id"]))
    build.status = terminal
    db_session.add(build)
    db_session.commit()

    resp = _create(client, ARTIFACT, user["id"])

    assert resp.status_code == 201, resp.text
    assert resp.json()["id"] != first["id"]
    assert len(db_session.exec(select(BuildORM)).all()) == 2


def test_two_users_may_each_build_their_own_artifact(client, store):
    one = create_user(client, USER_EMAIL)
    two = create_user(client, OTHER_EMAIL)
    store.upload(one["id"], ARTIFACT)
    store.upload(two["id"], OTHER_ARTIFACT)

    first = _create(client, ARTIFACT, one["id"], headers=USER_AUTH_HEADER)
    second = _create(client, OTHER_ARTIFACT, two["id"], headers=OTHER_AUTH_HEADER)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["user_id"] == one["id"]
    assert second.json()["user_id"] == two["id"]


# ---------------------------------------------------------------------------
# Reading a build
# ---------------------------------------------------------------------------


def test_owner_reads_their_build(client, store, user, db_session):
    build = _seed(db_session, user_id=user["id"], artifact_id=ARTIFACT)

    resp = client.get(f"/api/users/{build.user_id}/builds/{build.id}", headers=USER_AUTH_HEADER)

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(build.id)
    assert body["status"] == BUILD_STATUS_QUEUED
    assert body["artifact_id"] == ARTIFACT
    assert body["image"] is None


def test_another_users_build_is_indistinguishable_from_a_missing_one(client, db_session):
    """Under your own account, someone else's build id reads exactly like a
    missing one -- naming their account instead is refused earlier, with 403."""
    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)
    missing = "00000000-0000-4000-8000-000000000000"

    theirs = client.get(_builds(other["id"], build.id), headers=OTHER_AUTH_HEADER)
    absent = client.get(_builds(other["id"], missing), headers=OTHER_AUTH_HEADER)

    assert theirs.status_code == absent.status_code == 404
    assert theirs.json() == absent.json()

    # Naming the owner's account is a different refusal, and an earlier one.
    assert client.get(_builds(owner["id"], build.id), headers=OTHER_AUTH_HEADER).status_code == 403


def test_admin_may_read_any_build(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    resp = client.get(f"/api/users/{build.user_id}/builds/{build.id}", headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.json()["user_id"] == owner["id"]


def test_succeeded_build_exposes_its_image(client, db_session):
    owner = create_user(client, USER_EMAIL)
    image = f"{owner['id']}@sha256:{'c' * 64}"
    build = _seed(
        db_session,
        user_id=owner["id"],
        artifact_id=ARTIFACT,
        status=BUILD_STATUS_SUCCEEDED,
        image=image,
    )

    body = client.get(f"/api/users/{build.user_id}/builds/{build.id}", headers=USER_AUTH_HEADER).json()

    assert body["image"] == image
    assert isinstance(body["image"], str)


def test_build_response_carries_no_deployment_reference(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    body = client.get(f"/api/users/{build.user_id}/builds/{build.id}", headers=USER_AUTH_HEADER).json()

    assert not [k for k in body if "deployment" in k]
    assert "job_id" not in body and "log" not in body


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_listing_returns_the_callers_builds_most_recent_first(client, db_session):
    owner = create_user(client, USER_EMAIL)
    base = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    ids = [
        str(
            _seed(
                db_session,
                user_id=owner["id"],
                artifact_id=chr(ord("a") + n) * 32,
                created_at=base + timedelta(minutes=n),
            ).id
        )
        for n in range(3)
    ]

    body = client.get(_builds(owner["id"]), headers=USER_AUTH_HEADER).json()

    assert [b["id"] for b in body] == list(reversed(ids))


def test_listing_excludes_other_users_builds(client, db_session):
    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    mine = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)
    _seed(db_session, user_id=other["id"], artifact_id=OTHER_ARTIFACT)

    body = client.get(_builds(owner["id"]), headers=USER_AUTH_HEADER).json()

    assert [b["id"] for b in body] == [str(mine.id)]


def test_listing_is_empty_for_a_user_with_no_builds(client, db_session):
    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    _seed(db_session, user_id=other["id"], artifact_id=ARTIFACT)

    assert client.get(_builds(owner["id"]), headers=USER_AUTH_HEADER).json() == []


def test_admin_may_list_another_users_builds(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    resp = client.get(_builds(owner["id"]), headers=AUTH_HEADER)

    assert resp.status_code == 200
    assert [b["id"] for b in resp.json()] == [str(build.id)]


def test_a_regular_user_cannot_list_another_users_builds(client, db_session):
    owner = create_user(client, USER_EMAIL)
    create_user(client, OTHER_EMAIL)
    _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    resp = client.get(_builds(owner["id"]), headers=OTHER_AUTH_HEADER)

    assert resp.status_code == 403


def test_the_root_level_build_paths_are_gone(client, db_session):
    """The relocation is a hard cut: nothing answers at the old paths."""
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    assert client.get("/api/builds", headers=USER_AUTH_HEADER).status_code == 404
    assert client.get(f"/api/builds/{build.id}", headers=USER_AUTH_HEADER).status_code == 404
    assert client.get(f"/api/builds/{build.id}/log", headers=USER_AUTH_HEADER).status_code == 404
    assert client.post(
        "/api/builds", json={"artifact_id": ARTIFACT}, headers=USER_AUTH_HEADER
    ).status_code == 404


def test_creating_a_build_under_another_account_is_refused(client, store, db_session):
    owner = create_user(client, USER_EMAIL)
    create_user(client, OTHER_EMAIL)
    store.upload(owner["id"], ARTIFACT)

    resp = client.post(
        _builds(owner["id"]), json={"artifact_id": ARTIFACT}, headers=OTHER_AUTH_HEADER
    )

    assert resp.status_code == 403
    assert db_session.exec(select(BuildORM)).all() == []


# ---------------------------------------------------------------------------
# The log endpoint
# ---------------------------------------------------------------------------

LOG = b"step 1: resolving\nstep 2: building\n"


def test_log_without_a_range_returns_everything_as_plain_text(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    resp = client.get(f"/api/users/{build.user_id}/builds/{build.id}/log", headers=USER_AUTH_HEADER)

    assert resp.status_code == 200
    assert resp.content == LOG
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.headers["accept-ranges"] == "bytes"


def test_range_read_returns_only_output_appended_since(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)
    read_so_far = len(b"step 1: resolving\n")

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log",
        headers={**USER_AUTH_HEADER, "Range": f"bytes={read_so_far}-"},
    )

    assert resp.status_code == 206
    assert resp.content == b"step 2: building\n"
    assert resp.headers["content-range"] == f"bytes {read_so_far}-{len(LOG) - 1}/*"


def test_a_growing_log_reports_an_unknown_total_length(client, db_session):
    """`/*`, never an asserted total: the build is still writing."""
    owner = create_user(client, USER_EMAIL)
    build = _seed(
        db_session, user_id=owner["id"], artifact_id=ARTIFACT, status=BUILD_STATUS_RUNNING, log=LOG
    )

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": "bytes=0-"}
    )

    assert resp.headers["content-range"].endswith("/*")
    assert f"/{len(LOG)}" not in resp.headers["content-range"]


def test_polling_at_end_of_log_returns_an_empty_partial_response(client, db_session):
    """The steady state of a polling loop, not an error — no 416."""
    owner = create_user(client, USER_EMAIL)
    build = _seed(
        db_session, user_id=owner["id"], artifact_id=ARTIFACT, status=BUILD_STATUS_RUNNING, log=LOG
    )

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log",
        headers={**USER_AUTH_HEADER, "Range": f"bytes={len(LOG)}-"},
    )

    assert resp.status_code == 206
    assert resp.text == ""
    assert "content-range" not in resp.headers


def test_polling_past_the_end_of_log_is_also_empty_rather_than_an_error(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log",
        headers={**USER_AUTH_HEADER, "Range": f"bytes={len(LOG) + 5000}-"},
    )

    assert resp.status_code == 206
    assert resp.text == ""


def test_an_empty_log_polls_cleanly_from_zero(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": "bytes=0-"}
    )

    assert resp.status_code == 206
    assert resp.text == ""


def test_a_closed_range_returns_exactly_that_window(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": "bytes=0-3"}
    )

    assert resp.status_code == 206
    assert resp.content == LOG[:4]
    assert resp.headers["content-range"] == "bytes 0-3/*"


@pytest.mark.parametrize(
    "header",
    ["bytes=-20", "bytes=0-3,8-10", "items=0-3", "bytes=abc-", "bytes=9-2", "garbage"],
)
def test_an_unsupported_range_is_ignored_and_served_in_full(client, db_session, header):
    """RFC 7233 permits ignoring a range a server does not understand."""
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    resp = client.get(f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": header})

    assert resp.status_code == 200
    assert resp.content == LOG


@pytest.mark.parametrize(
    "status", [BUILD_STATUS_QUEUED, BUILD_STATUS_RUNNING, BUILD_STATUS_SUCCEEDED, BUILD_STATUS_FAILED]
)
def test_every_log_response_carries_the_build_status(client, db_session, status):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, status=status, log=LOG)
    url = f"/api/users/{build.user_id}/builds/{build.id}/log"

    full = client.get(url, headers=USER_AUTH_HEADER)
    partial = client.get(url, headers={**USER_AUTH_HEADER, "Range": "bytes=5-"})
    empty = client.get(url, headers={**USER_AUTH_HEADER, "Range": f"bytes={len(LOG)}-"})

    for resp in (full, partial, empty):
        assert resp.headers["X-Build-Status"] == status


def test_log_offsets_are_bytes_not_characters(client, db_session):
    """Multi-byte output must not shift a client's offsets."""
    owner = create_user(client, USER_EMAIL)
    log = "✓ done\n".encode("utf-8")  # 7 characters, 9 bytes
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=log)
    encoded = log

    full = client.get(f"/api/users/{build.user_id}/builds/{build.id}/log", headers=USER_AUTH_HEADER)
    tail = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": "bytes=3-"}
    )

    assert full.content == encoded
    assert tail.content == encoded[3:]
    assert tail.headers["content-range"] == f"bytes 3-{len(encoded) - 1}/*"


def test_polling_a_growing_log_reassembles_exactly(client, db_session):
    """The whole point: concatenated range reads equal the final log."""
    owner = create_user(client, USER_EMAIL)
    build = _seed(
        db_session, user_id=owner["id"], artifact_id=ARTIFACT, status=BUILD_STATUS_RUNNING, log=b""
    )
    url = f"/api/users/{build.user_id}/builds/{build.id}/log"
    collected = b""

    for chunk in ("resolving…\n", "building…\n", "pushing…\n"):
        build.log += chunk.encode("utf-8")
        db_session.add(build)
        db_session.commit()
        resp = client.get(url, headers={**USER_AUTH_HEADER, "Range": f"bytes={len(collected)}-"})
        assert resp.status_code == 206
        assert resp.content == chunk.encode("utf-8")
        collected += resp.content

    # Nothing new: an empty 206, and the loop needs no special case.
    idle = client.get(url, headers={**USER_AUTH_HEADER, "Range": f"bytes={len(collected)}-"})
    assert idle.status_code == 206 and idle.content == b""
    assert collected == build.log


def test_another_users_log_is_not_readable(client, db_session):
    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    resp = client.get(_builds(other["id"], build.id, "log"), headers=OTHER_AUTH_HEADER)

    assert resp.status_code == 404
    assert LOG.decode() not in resp.text

    # Naming the owner's account is refused before the log is ever read.
    refused = client.get(_builds(owner["id"], build.id, "log"), headers=OTHER_AUTH_HEADER)
    assert refused.status_code == 403
    assert LOG.decode() not in refused.text


# ---------------------------------------------------------------------------
# Service-level scoping
# ---------------------------------------------------------------------------


def test_service_reads_are_scoped_to_the_owner(client, db_session):
    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=LOG)

    assert build_service.get_build(db_session, build_id=build.id, user_id=owner["id"]).id == build.id
    with pytest.raises(NotFoundException):
        build_service.get_build(db_session, build_id=build.id, user_id=other["id"])


def test_service_admin_override_reads_across_users(client, db_session):
    owner = create_user(client, USER_EMAIL)
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    assert build_service.get_build(db_session, build_id=build.id, user_id=None).id == build.id
    assert [b.id for b in build_service.list_builds(db_session, user_id=None)] == [build.id]


def test_service_rejects_a_malformed_artifact_id_before_touching_the_store(
    client, db_session, store, user
):
    with pytest.raises(ValidationException):
        build_service.create_build(
            db_session, user_id=user["id"], payload=BuildCreate(artifact_id="nope")
        )
    assert store.checked == []


def test_a_creation_race_adopts_the_winners_build(client, db_session, store, user, monkeypatch):
    """The partial unique index is the arbiter; the loser must not 500.

    Simulated by hiding the existing build from the pre-check exactly once, so
    the insert reaches the database and is refused there — which is what a real
    concurrent request does.
    """
    store.upload(user["id"], ARTIFACT)
    winner = _seed(db_session, user_id=user["id"], artifact_id=ARTIFACT)

    real = build_service._find_open_build
    calls = {"n": 0}

    def racy(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(build_service, "_find_open_build", racy)

    result = build_service.create_build(
        db_session, user_id=user["id"], payload=BuildCreate(artifact_id=ARTIFACT)
    )

    assert result.created is False
    assert result.build.id == winner.id
    assert len(db_session.exec(select(BuildORM)).all()) == 1


def test_a_race_lost_to_another_user_is_a_conflict_not_a_crash(client, db_session, store):
    """Artifact ids are uuid4 so this is practically unreachable — but it must
    surface as a 409, never an unhandled IntegrityError."""
    from app.services.errors import IntegrityException

    owner = create_user(client, USER_EMAIL)
    other = create_user(client, OTHER_EMAIL)
    store.upload(other["id"], ARTIFACT)
    _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT)

    with pytest.raises(IntegrityException):
        build_service.create_build(
            db_session, user_id=other["id"], payload=BuildCreate(artifact_id=ARTIFACT)
        )


def test_log_survives_bytes_that_are_not_valid_text(client, db_session):
    """The reason the column is bytea rather than text.

    A NUL byte cannot be stored in a Postgres `text` value at all, so a build
    emitting one would fail its log write on every worker pass and wedge
    itself; invalid UTF-8 would otherwise force a lossy decode that shifts the
    very byte offsets clients poll with.
    """
    owner = create_user(client, USER_EMAIL)
    hostile = b"compiling\x00\xff\xfe raw \x80 bytes\ndone\n"
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=hostile)

    full = client.get(f"/api/users/{build.user_id}/builds/{build.id}/log", headers=USER_AUTH_HEADER)
    tail = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": "bytes=9-"}
    )

    assert full.content == hostile
    assert tail.content == hostile[9:]
    assert tail.headers["content-range"] == f"bytes 9-{len(hostile) - 1}/*"


def test_log_length_is_the_byte_length_the_client_polls_with(client, db_session):
    """Offsets and the stored value's length are the same number — which is
    what makes `build_log_max_bytes` an exact slice for the worker."""
    owner = create_user(client, USER_EMAIL)
    log = "héllo ✓\n".encode("utf-8")
    build = _seed(db_session, user_id=owner["id"], artifact_id=ARTIFACT, log=log)

    resp = client.get(
        f"/api/users/{build.user_id}/builds/{build.id}/log", headers={**USER_AUTH_HEADER, "Range": f"bytes={len(log)}-"}
    )

    assert len(log) > len(log.decode("utf-8"))
    assert resp.status_code == 206 and resp.content == b""
