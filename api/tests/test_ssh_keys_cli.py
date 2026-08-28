"""`caelus ssh-key` parity with the REST collection."""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import pytest
import yaml

from sqlmodel import Session

from app.db import get_engine
from app.models import UserORM
from app.services import ssh_keys as service
from tests.conftest import cli_runner  # noqa: F401

_counter = itertools.count()


def pub(tmp_path: Path, key_type="ed25519", extra=(), comment="alice@laptop") -> str:
    path = tmp_path / f"cli-{key_type}-{next(_counter)}"
    subprocess.run(
        ["ssh-keygen", "-t", key_type, "-N", "", "-C", comment, "-f", str(path), *extra],
        check=True,
        capture_output=True,
    )
    return str(path) + ".pub"


def _make_user(email: str, is_admin: bool = False) -> int:
    with Session(get_engine()) as session:
        user = UserORM(email=email, is_admin=is_admin)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


@pytest.fixture
def actor(cli_runner):
    return _make_user("operator@example.com")


def run(cli_runner, *args, email="operator@example.com"):
    runner, app = cli_runner
    return runner.invoke(app, ["--as-user", email, "ssh-key", *args])


def keys_for(user_id: int):
    with Session(get_engine()) as session:
        return service.list_keys(session, user_id=user_id)


def add_key_for(user_id: int, material: str):
    with Session(get_engine()) as session:
        return service.add_key(session, user_id=user_id, public_key=material)


def test_add_from_file_and_list(cli_runner, actor, tmp_path):
    result = run(cli_runner, "add", pub(tmp_path))
    assert result.exit_code == 0, result.output
    added = yaml.safe_load(result.output)
    assert added["fingerprint"].startswith("SHA256:")
    assert added["label"] == "alice@laptop"

    listed = yaml.safe_load(run(cli_runner, "list").output)
    assert [k["fingerprint"] for k in listed] == [added["fingerprint"]]


def test_add_accepts_the_key_line_itself(cli_runner, actor, tmp_path):
    line = Path(pub(tmp_path)).read_text().strip()
    result = run(cli_runner, "add", line)
    assert result.exit_code == 0, result.output


def test_add_rejects_invalid_key_like_the_api(cli_runner, actor):
    result = run(cli_runner, "add", "gibberish")
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_add_rejects_a_private_key(cli_runner, actor, tmp_path):
    path = tmp_path / "priv"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(path)],
        check=True,
        capture_output=True,
    )
    result = run(cli_runner, "add", str(path))
    assert result.exit_code == 1
    assert "private key" in result.output.lower()


def test_add_rejects_undersized_rsa_like_the_api(cli_runner, actor, tmp_path):
    result = run(cli_runner, "add", pub(tmp_path, "rsa", ("-b", "1024")))
    assert result.exit_code == 1
    assert "2048" in result.output


def test_rm_removes_the_key(cli_runner, actor, tmp_path):
    added = yaml.safe_load(run(cli_runner, "add", pub(tmp_path)).output)
    result = run(cli_runner, "rm", added["fingerprint"])
    assert result.exit_code == 0, result.output
    assert keys_for(actor) == []


def test_rm_of_unknown_fingerprint_fails(cli_runner, actor):
    result = run(cli_runner, "rm", "SHA256:nope")
    assert result.exit_code == 1
    assert "Error:" in result.output


def test_operator_revokes_another_users_key(cli_runner, tmp_path):
    _make_user("root@example.com", is_admin=True)
    owner = _make_user("owner@example.com")
    stored = add_key_for(owner, Path(pub(tmp_path)).read_text())

    runner, app = cli_runner
    result = runner.invoke(
        app,
        ["--as-user", "root@example.com", "ssh-key", "rm", stored.fingerprint,
         "--user-id", str(owner)],
    )
    assert result.exit_code == 0, result.output
    assert keys_for(owner) == []


def test_non_admin_cannot_reach_another_account(cli_runner, tmp_path):
    owner = _make_user("owner@example.com")
    _make_user("nosy@example.com")
    stored = add_key_for(owner, Path(pub(tmp_path)).read_text())

    runner, app = cli_runner
    result = runner.invoke(
        app,
        ["--as-user", "nosy@example.com", "ssh-key", "rm", stored.fingerprint,
         "--user-id", str(owner)],
    )
    assert result.exit_code == 1
    assert len(keys_for(owner)) == 1
