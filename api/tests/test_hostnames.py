"""Tests for the hostname validation service and API endpoint."""
import socket
from unittest.mock import patch

import pytest

from app.config import CaelusSettings
from app.services.errors import HostnameException
from app.services.hostnames import (
    _check_format,
    _check_reserved,
    _check_available,
    _check_resolving,
    require_valid_hostname_for_deployment,
)
from app.models import DeploymentORM, UserORM, ProductORM, ProductTemplateVersionORM
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_PROVISIONING,
    DEPLOYMENT_STATUS_DELETED,
)
from tests.conftest import client, db_session


def _settings(**overrides) -> CaelusSettings:
    """Build a CaelusSettings with test defaults, ignoring env vars."""
    defaults = {"reserved_hostnames": [], "lb_ips": []}
    return CaelusSettings(**{**defaults, **overrides}, _env_file=None)


@pytest.fixture
def seed_parents(db_session):
    """Create the minimum parent rows (user, product, template) so that
    DeploymentORM inserts satisfy foreign key constraints."""
    user = UserORM(email="seed@example.com")
    db_session.add(user)
    db_session.flush()

    product = ProductORM(name="seed-product")
    db_session.add(product)
    db_session.flush()

    template = ProductTemplateVersionORM(
        product_id=product.id,
        chart_ref="oci://example/seed",
        chart_version="1.0.0",
    )
    db_session.add(template)
    db_session.flush()

    return {"user_id": user.id, "template_id": template.id}


# ── Format check ──────────────────────────────────────────────────────


class TestCheckFormat:
    def test_valid_fqdn(self):
        _check_format("myapp.example.com")

    def test_valid_fqdn_with_trailing_dot(self):
        _check_format("myapp.example.com.")

    def test_valid_single_char_labels(self):
        _check_format("a.b.com")

    def test_valid_hyphens_in_middle(self):
        _check_format("my-app.ex-ample.com")

    def test_rejects_empty_string(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("")

    def test_rejects_single_label(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("localhost")

    def test_rejects_too_long(self):
        fqdn = "a" * 64 + ".example.com"  # label > 63 chars
        with pytest.raises(HostnameException, match="invalid"):
            _check_format(fqdn)

    def test_rejects_total_too_long(self):
        fqdn = ".".join(["a" * 50] * 6)  # 50*6 + 5 dots = 305 chars
        with pytest.raises(HostnameException, match="invalid"):
            _check_format(fqdn)

    def test_rejects_leading_hyphen(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("-bad.example.com")

    def test_rejects_trailing_hyphen(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("bad-.example.com")

    def test_rejects_empty_label(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("bad..example.com")

    def test_rejects_underscore(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("bad_host.example.com")

    def test_rejects_space(self):
        with pytest.raises(HostnameException, match="invalid"):
            _check_format("bad host.example.com")


# ── Reserved check ────────────────────────────────────────────────────


class TestCheckReserved:
    def test_not_reserved_passes(self):
        _check_reserved("myapp.example.com", _settings(reserved_hostnames=["smtp.example.com"]))

    def test_reserved_raises(self):
        with pytest.raises(HostnameException, match="reserved"):
            _check_reserved("smtp.example.com", _settings(reserved_hostnames=["smtp.example.com"]))

    def test_empty_reserved_list_passes(self):
        _check_reserved("anything.example.com", _settings(reserved_hostnames=[]))


# ── Availability check ────────────────────────────────────────────────


class TestCheckAvailable:
    def test_available_passes(self, db_session):
        _check_available(db_session, "free.example.com")

    def test_in_use_raises(self, db_session, seed_parents):
        dep = DeploymentORM(
            user_id=seed_parents["user_id"],
            desired_template_id=seed_parents["template_id"],
            hostname="taken.example.com",
            status=DEPLOYMENT_STATUS_PROVISIONING,
            deployment_uid="test-uid",
        )
        db_session.add(dep)
        db_session.flush()
        with pytest.raises(HostnameException, match="in_use"):
            _check_available(db_session, "taken.example.com")

    def test_deleted_deployment_not_in_use(self, db_session, seed_parents):
        dep = DeploymentORM(
            user_id=seed_parents["user_id"],
            desired_template_id=seed_parents["template_id"],
            hostname="recycled.example.com",
            status=DEPLOYMENT_STATUS_DELETED,
            deployment_uid="test-uid-2",
        )
        db_session.add(dep)
        db_session.flush()
        _check_available(db_session, "recycled.example.com")


# ── DNS resolution check ─────────────────────────────────────────────


class TestCheckResolving:
    def test_skipped_when_lb_ips_empty(self):
        # Should not raise even if DNS would fail
        _check_resolving("nonexistent.example.test", _settings(lb_ips=[]))

    def test_passes_when_all_ips_match(self):
        fake_results = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0)),
        ]
        with patch("app.services.hostnames.socket.getaddrinfo", return_value=fake_results):
            _check_resolving("good.example.com", _settings(lb_ips=["1.2.3.4", "2001:db8::1"]))

    def test_passes_ipv4_only_subset(self):
        fake_results = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
        ]
        with patch("app.services.hostnames.socket.getaddrinfo", return_value=fake_results):
            _check_resolving("v4only.example.com", _settings(lb_ips=["1.2.3.4", "2001:db8::1"]))

    def test_fails_when_ip_outside_lb_set(self):
        fake_results = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.2.3.4", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("9.9.9.9", 0)),
        ]
        with patch("app.services.hostnames.socket.getaddrinfo", return_value=fake_results):
            with pytest.raises(HostnameException, match="not_resolving"):
                _check_resolving("mixed.example.com", _settings(lb_ips=["1.2.3.4"]))

    def test_fails_when_dns_does_not_resolve(self):
        with patch(
            "app.services.hostnames.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            with pytest.raises(HostnameException, match="not_resolving"):
                _check_resolving("nxdomain.example.com", _settings(lb_ips=["1.2.3.4"]))

    def test_fails_when_no_results_returned(self):
        with patch("app.services.hostnames.socket.getaddrinfo", return_value=[]):
            with pytest.raises(HostnameException, match="not_resolving"):
                _check_resolving("empty.example.com", _settings(lb_ips=["1.2.3.4"]))


# ── Orchestration (short-circuit behavior) ────────────────────────────


class TestRequireValidHostname:
    def test_valid_hostname_returns_none(self, db_session):
        result = require_valid_hostname_for_deployment(
            db_session, "valid.example.com", settings=_settings(),
        )
        assert result is None

    def test_short_circuits_on_format(self, db_session):
        """Format failure should not touch the DB or DNS."""
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "-invalid", settings=_settings(lb_ips=["1.2.3.4"]),
            )
        assert exc_info.value.reason == "invalid"

    def test_short_circuits_on_reserved(self, db_session):
        """Reserved failure should not check availability or DNS."""
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "smtp.example.com",
                settings=_settings(reserved_hostnames=["smtp.example.com"], lb_ips=["1.2.3.4"]),
            )
        assert exc_info.value.reason == "reserved"

    def test_short_circuits_on_in_use(self, db_session, seed_parents):
        """In-use failure should not perform DNS resolution."""
        dep = DeploymentORM(
            user_id=seed_parents["user_id"],
            desired_template_id=seed_parents["template_id"],
            hostname="taken.example.com",
            status=DEPLOYMENT_STATUS_PROVISIONING,
            deployment_uid="test-uid",
        )
        db_session.add(dep)
        db_session.flush()
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "taken.example.com",
                settings=_settings(lb_ips=["1.2.3.4"]),
            )
        assert exc_info.value.reason == "in_use"


# ── API endpoint tests ────────────────────────────────────────────────


class TestHostnameCheckEndpoint:
    def test_usable_hostname(self, client):
        resp = client.get("/api/hostnames/myapp.example.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fqdn"] == "myapp.example.com"
        assert data["usable"] is True
        assert data["reason"] is None

    def test_invalid_format(self, client):
        resp = client.get("/api/hostnames/-bad..host")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fqdn"] == "-bad..host"
        assert data["usable"] is False
        assert data["reason"] == "invalid"

    def test_reserved_hostname(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.services.hostnames.get_settings",
            lambda: _settings(reserved_hostnames=["smtp.example.com"]),
        )
        resp = client.get("/api/hostnames/smtp.example.com")
        assert resp.status_code == 200
        assert resp.json()["usable"] is False
        assert resp.json()["reason"] == "reserved"

    def test_hostname_in_use(self, client, db_session):
        # Create a product, template, and deployment to occupy the hostname
        product = client.post("/api/products", json={"name": "hn-test", "description": "test"})
        product_id = product.json()["id"]
        template = client.post(
            f"/api/products/{product_id}/templates",
            json={
                "chart_ref": "oci://example/chart",
                "chart_version": "1.0.0",
                "values_schema_json": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "title": "hostname"},
                    },
                },
            },
        )
        template_id = template.json()["id"]
        user = client.post("/api/users", json={"email": "hn-test@example.com"})
        user_id = user.json()["id"]
        client.post(
            f"/api/users/{user_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"host": "occupied.example.com"},
            },
        )
        resp = client.get("/api/hostnames/occupied.example.com")
        assert resp.status_code == 200
        assert resp.json()["usable"] is False
        assert resp.json()["reason"] == "in_use"

    def test_not_resolving(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.services.hostnames.get_settings",
            lambda: _settings(lb_ips=["1.2.3.4"]),
        )
        with patch(
            "app.services.hostnames.socket.getaddrinfo",
            side_effect=socket.gaierror("nope"),
        ):
            resp = client.get("/api/hostnames/nxdomain.example.com")
        assert resp.status_code == 200
        assert resp.json()["usable"] is False
        assert resp.json()["reason"] == "not_resolving"

    def test_unauthenticated_returns_404(self, db_session):
        from starlette.testclient import TestClient
        from app.db import get_session
        from app.main import app as fastapi_app

        def override_get_db():
            yield db_session

        fastapi_app.dependency_overrides[get_session] = override_get_db
        with TestClient(fastapi_app) as no_auth_client:
            resp = no_auth_client.get("/api/hostnames/test.example.com")
            assert resp.status_code == 404
        fastapi_app.dependency_overrides.clear()

    def test_response_has_exactly_three_fields(self, client):
        resp = client.get("/api/hostnames/clean.example.com")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == {"fqdn", "usable", "reason"}
