"""Every command that connects presents the same username: the deployment id.

The edge admits one identifier and refuses everything else without saying why,
so a command deriving the username its own way fails as a bare authentication
refusal -- and it would fail for that command alone, which is the version of
this bug that is hardest to recognize. Asserted across all four together.
"""

from __future__ import annotations

import subprocess

import pytest

from freepod import EXIT_OK
from freepod import keys as keys_module
from freepod.cli import main

from test_db_proxy import DATABASE, Platform, key_entry, project_at
from test_shell import DEPLOYMENT_ID, DEPLOYMENT_NAME, EDGE


@pytest.fixture
def capture_any_connection(monkeypatch):
    """The argv of whichever of the three ways to connect the command takes."""
    captured: dict = {}

    def interactive(args):
        captured.update(args=args)
        return 0

    def run(args, **kwargs):
        captured.update(args=args)
        return subprocess.CompletedProcess(args, 0)

    def transfer(args, script):
        captured.update(args=args)
        return 0

    monkeypatch.setattr("freepod.ssh.require_ssh", lambda: "/usr/bin/ssh")
    monkeypatch.setattr("freepod.ssh.require_sftp", lambda: "/usr/bin/sftp")
    monkeypatch.setattr("freepod.ssh.run_interactive", interactive)
    monkeypatch.setattr("freepod.ssh.run", run)
    monkeypatch.setattr("freepod.copy.run", transfer)
    return captured


@pytest.fixture
def ready(stub_api, cached_credential, tmp_path, monkeypatch):
    """A ready deployment with a database, and this machine's registered key."""
    project_at(tmp_path)
    keys_module.generate_keypair(keys_module.generated_key_path())
    stub_api(
        Platform(
            deployment={
                "id": DEPLOYMENT_ID,
                "name": DEPLOYMENT_NAME,
                "status": "ready",
            },
            database=DATABASE,
            keys=[key_entry()],
        )
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _user_argument(args: list[str]) -> str:
    """The `user@host` the client hands ssh as its destination."""
    destinations = [a for a in args if a.endswith("@" + EDGE["host"])]
    assert len(destinations) == 1, args
    return destinations[0].partition("@")[0]


@pytest.mark.parametrize(
    "argv",
    [
        ["shell"],
        ["db", "proxy", "--port", "5432"],
        ["db", "shell"],
        ["cp", "local.txt", ":/app/local.txt"],
    ],
    ids=["shell", "db-proxy", "db-shell", "cp"],
)
def test_every_command_presents_the_namespace(ready, capture_any_connection, argv):
    (ready / "local.txt").write_text("x", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == EXIT_OK

    user = _user_argument(capture_any_connection["args"])
    assert user == DEPLOYMENT_ID
    assert DEPLOYMENT_NAME not in user
