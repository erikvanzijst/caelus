"""The command surface wired up so far: login, logout, whoami."""

from __future__ import annotations

import httpx
import pytest

from freepod import EXIT_NOT_AUTHENTICATED, EXIT_OK, EXIT_USAGE
from freepod.auth import load_refresh_token, store_refresh_token
from freepod.cli import main

from conftest import json_response, sequence, text_response


@pytest.fixture
def stub_api(monkeypatch):
    """Replace the command's API client with one on a mock transport."""

    def install(handler):
        from freepod.api import ApiClient
        from freepod.cli import Context

        def client(self, session):
            return ApiClient(
                self.env,
                session,
                client=httpx.Client(transport=httpx.MockTransport(handler)),
                backoff_base=0,
            )

        monkeypatch.setattr(Context, "client", client)

    return install


@pytest.fixture
def cached_credential(monkeypatch):
    """A cached refresh token, and a Keycloak that honors it."""
    from freepod import auth

    store_refresh_token("prod", "freepod-cli-prod", "prod-refresh")
    monkeypatch.setattr(
        auth, "post_form", lambda url, fields, timeout=30: {"access_token": "fresh-at"}
    )


ME = {"id": 7, "email": "erik@example.com", "is_admin": False}


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def test_help_exits_zero(capsys):
    assert main(["--help"]) == EXIT_OK
    assert "login" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["login", "logout", "whoami"])
def test_every_command_has_help(command, capsys):
    assert main([command, "--help"]) == EXIT_OK
    capsys.readouterr()


def test_an_unknown_environment_is_a_usage_error(capsys):
    assert main(["--env", "staging", "logout"]) == EXIT_USAGE
    assert "staging" in capsys.readouterr().err


def test_an_unknown_command_is_a_usage_error(capsys):
    assert main(["frobnicate"]) == EXIT_USAGE
    capsys.readouterr()


# --------------------------------------------------------------------------
# logout
# --------------------------------------------------------------------------


def test_logout_discards_the_cached_credential(capsys):
    store_refresh_token("prod", "freepod-cli-prod", "prod-refresh")

    assert main(["logout"]) == EXIT_OK

    assert load_refresh_token("prod") is None
    assert "Discarded" in capsys.readouterr().err


def test_logout_with_nothing_cached_says_so(capsys):
    assert main(["logout"]) == EXIT_OK
    assert "No cached credential" in capsys.readouterr().err


def test_logout_states_that_it_revokes_nothing(capsys):
    main(["logout"])
    stderr = capsys.readouterr().err
    assert "remains valid on the platform" in stderr
    assert "Keycloak account console" in stderr


def test_logout_targets_only_the_selected_environment(capsys):
    store_refresh_token("prod", "freepod-cli-prod", "prod-refresh")
    store_refresh_token("dev", "freepod-cli-dev", "dev-refresh")

    assert main(["--env", "dev", "logout"]) == EXIT_OK

    assert load_refresh_token("dev") is None
    assert load_refresh_token("prod") == "prod-refresh"
    capsys.readouterr()


# --------------------------------------------------------------------------
# whoami
# --------------------------------------------------------------------------


def test_whoami_reports_the_identity(stub_api, cached_credential, capsys):
    stub_api(sequence(json_response(200, ME)))

    assert main(["whoami"]) == EXIT_OK

    stdout = capsys.readouterr().out
    assert "erik@example.com" in stdout
    assert "user id: 7" in stdout


def test_whoami_without_a_credential_exits_three(capsys):
    assert main(["whoami"]) == EXIT_NOT_AUTHENTICATED
    assert "not authenticated" in capsys.readouterr().err


def test_whoami_never_opens_a_browser(monkeypatch, capsys):
    from freepod.auth import Session

    monkeypatch.setattr(
        Session, "login", lambda self: pytest.fail("whoami must not start a login")
    )
    assert main(["whoami"]) == EXIT_NOT_AUTHENTICATED
    capsys.readouterr()


def test_whoami_keeps_diagnostics_off_stdout(stub_api, cached_credential, capsys):
    """A redirected stdout carries only the result."""
    stub_api(sequence(json_response(200, ME)))

    main(["whoami"])

    captured = capsys.readouterr()
    assert "Environment" not in captured.out
    assert "Environment 'prod'" in captured.err


def test_whoami_surfaces_a_401_as_not_authenticated(stub_api, cached_credential, capsys):
    stub_api(sequence(text_response(401)))

    assert main(["whoami"]) == EXIT_NOT_AUTHENTICATED
    assert "401" in capsys.readouterr().err


# --------------------------------------------------------------------------
# login
# --------------------------------------------------------------------------


def test_login_reuses_a_valid_cached_credential(stub_api, cached_credential, monkeypatch, capsys):
    from freepod.auth import Session

    monkeypatch.setattr(
        Session, "login", lambda self: pytest.fail("a valid credential must not prompt a login")
    )
    stub_api(sequence(json_response(200, ME)))

    assert main(["login"]) == EXIT_OK

    stderr = capsys.readouterr().err
    assert "Authenticated as erik@example.com" in stderr
    assert "cached refresh token" in stderr


def test_login_force_ignores_the_cache(stub_api, cached_credential, monkeypatch, capsys):
    from freepod.auth import Session

    logins = []

    def fake_login(self):
        logins.append(True)
        self.access_token = "fresh-at"
        self.flow_used = "device"

    monkeypatch.setattr(Session, "login", fake_login)
    stub_api(sequence(json_response(200, ME)))

    assert main(["login", "--force"]) == EXIT_OK

    assert logins == [True]
    capsys.readouterr()


def test_login_reports_which_flow_it_used(stub_api, cached_credential, monkeypatch, capsys):
    from freepod.auth import Session

    def fake_login(self):
        self.access_token = "fresh-at"
        self.flow_used = "device"

    monkeypatch.setattr(Session, "login", fake_login)
    stub_api(sequence(json_response(200, ME)))

    main(["login", "--force"])

    assert "flow       : device" in capsys.readouterr().err


def test_login_passes_the_forced_flow_through(monkeypatch, stub_api, capsys):
    from freepod.auth import Session

    seen = {}

    def fake_login(self):
        seen["flow"] = self.choose_flow()[0]
        self.access_token = "fresh-at"

    monkeypatch.setattr(Session, "login", fake_login)
    monkeypatch.setattr(
        "freepod.auth.detect_browser",
        lambda: pytest.fail("detection must not run when the flow is forced"),
    )
    stub_api(sequence(json_response(200, ME)))

    main(["login", "--device"])

    assert seen["flow"] == "device"
    capsys.readouterr()


def test_login_writes_no_token_to_either_stream(stub_api, cached_credential, capsys):
    stub_api(sequence(json_response(200, ME)))

    main(["--verbose", "login"])

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "fresh-at" not in combined
    assert "prod-refresh" not in combined


def test_the_timeout_flag_reaches_the_login_wait(monkeypatch, stub_api, capsys):
    from freepod.auth import Session

    seen = {}

    def fake_login(self):
        seen["timeout"] = self.timeout
        self.access_token = "fresh-at"

    monkeypatch.setattr(Session, "login", fake_login)
    stub_api(sequence(json_response(200, ME)))

    main(["--timeout", "42", "login"])

    assert seen["timeout"] == 42
    capsys.readouterr()


def test_the_login_wait_defaults_to_its_own_value(monkeypatch, stub_api, capsys):
    from freepod.auth import Session
    from freepod.config import LOGIN_WAIT_SECONDS

    seen = {}

    def fake_login(self):
        seen["timeout"] = self.timeout
        self.access_token = "fresh-at"

    monkeypatch.setattr(Session, "login", fake_login)
    stub_api(sequence(json_response(200, ME)))

    main(["login"])

    assert seen["timeout"] == LOGIN_WAIT_SECONDS
    capsys.readouterr()
