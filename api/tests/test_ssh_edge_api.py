from __future__ import annotations

import pytest

from app.config import CaelusSettings

EDGE_HOST_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPI7YnsVFYJX4/w3XhyyLvxKuMQWR38GmlnW+faM6t/u"
)
EDGE_BLOB = "AAAAC3NzaC1lZDI1NTE5AAAAIPI7YnsVFYJX4/w3XhyyLvxKuMQWR38GmlnW+faM6t/u"


@pytest.fixture
def edge_settings(monkeypatch):
    """Point the endpoint's settings at a configured edge."""

    def _install(
        host_key: str = EDGE_HOST_KEY,
        host: str = "freepod.eu",
        port: int = 22,
    ):
        monkeypatch.setattr(
            "app.api.ssh.get_settings",
            lambda: CaelusSettings(
                ssh_edge_host_public_key=host_key,
                sftp_host=host,
                sftp_port=port,
                _env_file=None,
            ),
        )

    return _install


def test_ssh_edge_returns_host_key_and_address(client, edge_settings):
    edge_settings()
    resp = client.get("/api/ssh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "freepod.eu"
    assert body["port"] == 22
    assert body["host_key"] == {"ssh-ed25519": EDGE_BLOB}


def test_ssh_edge_host_port_track_settings(client, edge_settings):
    edge_settings(host="dev.freepod.eu", port=23)
    body = client.get("/api/ssh").json()
    assert body["host"] == "dev.freepod.eu"
    assert body["port"] == 23


def test_ssh_edge_empty_host_key_when_unconfigured(client, edge_settings):
    edge_settings(host_key="")
    resp = client.get("/api/ssh")
    assert resp.status_code == 200
    assert resp.json()["host_key"] == {}


def test_ssh_edge_is_public(client, edge_settings):
    """No session required: the response is public key material."""
    edge_settings()
    resp = client.get("/api/ssh", headers={"X-Auth-Request-Email": ""})
    assert resp.status_code == 200
    assert resp.json()["host_key"] == {"ssh-ed25519": EDGE_BLOB}
