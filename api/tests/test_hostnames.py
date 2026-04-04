"""Tests for the hostname validation service and API endpoint."""
import socket
from unittest.mock import patch
from uuid import UUID

import pytest

from app.config import CaelusSettings
from app.services.errors import HostnameException
from app.services.hostnames import (
    _check_format,
    _check_wildcard_depth,
    _check_reserved,
    _check_available,
    _check_resolving,
    require_valid_hostname_for_deployment,
)
from app.db import get_session
from app.main import app as fastapi_app
from app.models import DeploymentORM, DeploymentReconcileJobORM, UserORM, ProductORM, ProductTemplateVersionORM
from app.services.jobs import JobService
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_PROVISIONING,
    DEPLOYMENT_STATUS_DELETED,
)
from sqlmodel import select
from starlette.testclient import TestClient

from tests.conftest import client, db_session
from tests.conftest import create_free_plan_template


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


# ── Wildcard depth check ─────────────────────────────────────────────


class TestCheckWildcardDepth:
    def test_single_level_prefix_passes(self):
        _check_wildcard_depth("myapp.dev.deprutser.be", _settings(wildcard_domains=["dev.deprutser.be"]))

    def test_multi_level_prefix_rejected(self):
        with pytest.raises(HostnameException, match="nested_subdomain"):
            _check_wildcard_depth("foo.bar.dev.deprutser.be", _settings(wildcard_domains=["dev.deprutser.be"]))

    def test_bare_wildcard_domain_rejected(self):
        with pytest.raises(HostnameException, match="nested_subdomain"):
            _check_wildcard_depth("dev.deprutser.be", _settings(wildcard_domains=["dev.deprutser.be"]))

    def test_non_wildcard_fqdn_skipped(self):
        _check_wildcard_depth("foo.bar.example.com", _settings(wildcard_domains=["dev.deprutser.be"]))

    def test_case_insensitive_matching(self):
        """The FQDN is already lowercased by require_valid_hostname_for_deployment,
        but verify the check works with lowercase input against a wildcard domain."""
        with pytest.raises(HostnameException, match="nested_subdomain"):
            _check_wildcard_depth("foo.bar.dev.deprutser.be", _settings(wildcard_domains=["dev.deprutser.be"]))

    def test_empty_wildcard_domains_skips(self):
        _check_wildcard_depth("foo.bar.example.com", _settings(wildcard_domains=[]))

    def test_multiple_wildcard_domains(self):
        settings = _settings(wildcard_domains=["dev.deprutser.be", "app.deprutser.be"])
        _check_wildcard_depth("myapp.app.deprutser.be", settings)
        with pytest.raises(HostnameException, match="nested_subdomain"):
            _check_wildcard_depth("a.b.app.deprutser.be", settings)


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
            name="test-name",
            namespace="test-namespace",
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
            name="test-name-2",
            namespace="test-namespace-2",
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

    def test_short_circuits_on_wildcard_depth(self, db_session):
        """Nested subdomain failure should not check reserved, availability, or DNS."""
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "foo.bar.dev.deprutser.be",
                settings=_settings(wildcard_domains=["dev.deprutser.be"], lb_ips=["1.2.3.4"]),
            )
        assert exc_info.value.reason == "nested_subdomain"

    def test_short_circuits_on_reserved(self, db_session):
        """Reserved failure should not check availability or DNS."""
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "smtp.example.com",
                settings=_settings(reserved_hostnames=["smtp.example.com"], lb_ips=["1.2.3.4"]),
            )
        assert exc_info.value.reason == "reserved"

    def test_mixed_case_detected_as_in_use(self, db_session, seed_parents):
        """Mixed-case FQDN should be detected as in-use when lowercase variant exists."""
        dep = DeploymentORM(
            user_id=seed_parents["user_id"],
            desired_template_id=seed_parents["template_id"],
            hostname="taken.example.com",
            status=DEPLOYMENT_STATUS_PROVISIONING,
            name="test-name-case",
            namespace="test-namespace-case",
        )
        db_session.add(dep)
        db_session.flush()
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "Taken.Example.COM",
                settings=_settings(),
            )
        assert exc_info.value.reason == "in_use"

    def test_reserved_matching_is_case_insensitive(self, db_session):
        """Reserved hostname check should match regardless of input case."""
        with pytest.raises(HostnameException) as exc_info:
            require_valid_hostname_for_deployment(
                db_session, "SMTP.Example.Com",
                settings=_settings(reserved_hostnames=["smtp.example.com"]),
            )
        assert exc_info.value.reason == "reserved"

    def test_short_circuits_on_in_use(self, db_session, seed_parents):
        """In-use failure should not perform DNS resolution."""
        dep = DeploymentORM(
            user_id=seed_parents["user_id"],
            desired_template_id=seed_parents["template_id"],
            hostname="taken.example.com",
            status=DEPLOYMENT_STATUS_PROVISIONING,
            name="test-name-3",
            namespace="test-namespace-3",
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
        # Make it the canonical template
        client.put(f"/api/products/{product_id}", json={"template_id": template_id})
        ptv_id = create_free_plan_template(db_session, product_id)
        user = client.post("/api/users", json={"email": "hn-test@example.com"})
        user_id = user.json()["id"]
        client.post(
            f"/api/users/{user_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"host": "occupied.example.com"},
                "plan_template_id": ptv_id,
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
        def override_get_db():
            yield db_session

        fastapi_app.dependency_overrides[get_session] = override_get_db
        with TestClient(fastapi_app) as no_auth_client:
            resp = no_auth_client.get("/api/hostnames/test.example.com")
            assert resp.status_code == 404
        fastapi_app.dependency_overrides.clear()

    def test_mixed_case_fqdn_normalized_in_response(self, client):
        resp = client.get("/api/hostnames/MyApp.Example.COM")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fqdn"] == "myapp.example.com"

    def test_response_has_exactly_three_fields(self, client):
        resp = client.get("/api/hostnames/clean.example.com")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == {"fqdn", "usable", "reason"}


# ── Domains endpoint tests ────────────────────────────────────────────


class TestDomainsEndpoint:
    def test_returns_configured_domains(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.hostnames.get_settings",
            lambda: _settings(wildcard_domains=["app.deprutser.be", "apps.example.com"]),
        )
        resp = client.get("/api/domains")
        assert resp.status_code == 200
        assert resp.json() == ["app.deprutser.be", "apps.example.com"]

    def test_returns_empty_list_when_unconfigured(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.api.hostnames.get_settings",
            lambda: _settings(wildcard_domains=[]),
        )
        resp = client.get("/api/domains")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_no_auth_required(self, db_session):
        def override_get_db():
            yield db_session

        fastapi_app.dependency_overrides[get_session] = override_get_db
        with TestClient(fastapi_app) as no_auth_client:
            resp = no_auth_client.get("/api/domains")
            assert resp.status_code == 200
        fastapi_app.dependency_overrides.clear()


# ── Server-side hostname enforcement tests ────────────────────────────


class TestServerSideEnforcement:
    def test_create_deployment_rejects_reserved_hostname(self, client, db_session, monkeypatch):
        monkeypatch.setattr(
            "app.services.hostnames.get_settings",
            lambda: _settings(reserved_hostnames=["reserved.example.com"]),
        )
        product = client.post("/api/products", json={"name": "enforce-prod", "description": "test"})
        product_id = product.json()["id"]
        template = client.post(
            f"/api/products/{product_id}/templates",
            json={
                "chart_ref": "oci://example/chart",
                "chart_version": "1.0.0",
                "values_schema_json": {
                    "type": "object",
                    "properties": {"host": {"type": "string", "title": "hostname"}},
                },
            },
        )
        template_id = template.json()["id"]
        # Make it the canonical template
        client.put(f"/api/products/{product_id}", json={"template_id": template_id})
        ptv_id = create_free_plan_template(db_session, product_id)
        user = client.post("/api/users", json={"email": "enforce@example.com"})
        user_id = user.json()["id"]

        resp = client.post(
            f"/api/users/{user_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"host": "reserved.example.com"},
                "plan_template_id": ptv_id,
            },
        )
        assert resp.status_code == 409
        assert "reserved" in resp.json()["detail"]

    def test_create_deployment_rejects_in_use_hostname(self, client, db_session):
        product = client.post("/api/products", json={"name": "enforce-inuse", "description": "test"})
        product_id = product.json()["id"]
        template = client.post(
            f"/api/products/{product_id}/templates",
            json={
                "chart_ref": "oci://example/chart",
                "chart_version": "1.0.0",
                "values_schema_json": {
                    "type": "object",
                    "properties": {"host": {"type": "string", "title": "hostname"}},
                },
            },
        )
        template_id = template.json()["id"]
        # Make it the canonical template
        client.put(f"/api/products/{product_id}", json={"template_id": template_id})
        ptv_id = create_free_plan_template(db_session, product_id)
        user = client.post("/api/users", json={"email": "enforce-inuse@example.com"})
        user_id = user.json()["id"]

        # First deployment succeeds
        resp1 = client.post(
            f"/api/users/{user_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"host": "taken.enforce.example.com"},
                "plan_template_id": ptv_id,
            },
        )
        assert resp1.status_code == 201

        # Second deployment with same hostname is rejected
        user2 = client.post("/api/users", json={"email": "enforce-inuse2@example.com"})
        user2_id = user2.json()["id"]
        resp2 = client.post(
            f"/api/users/{user2_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"host": "taken.enforce.example.com"},
                "plan_template_id": ptv_id,
            },
        )
        assert resp2.status_code == 409
        assert "in_use" in resp2.json()["detail"]

    def test_create_deployment_skips_validation_when_no_hostname(self, client, db_session):
        """Templates without a hostname-titled field should not trigger validation."""
        product = client.post("/api/products", json={"name": "enforce-nohost", "description": "test"})
        product_id = product.json()["id"]
        template = client.post(
            f"/api/products/{product_id}/templates",
            json={
                "chart_ref": "oci://example/chart",
                "chart_version": "1.0.0",
                "values_schema_json": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            },
        )
        template_id = template.json()["id"]
        # Make it the canonical template
        client.put(f"/api/products/{product_id}", json={"template_id": template_id})
        ptv_id = create_free_plan_template(db_session, product_id)
        user = client.post("/api/users", json={"email": "enforce-nohost@example.com"})
        user_id = user.json()["id"]

        resp = client.post(
            f"/api/users/{user_id}/deployments",
            json={
                "desired_template_id": template_id,
                "user_values_json": {"message": "hello"},
                "plan_template_id": ptv_id,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["deployment"]["hostname"] is None

    def test_update_deployment_allows_same_hostname(self, client, db_session):
        """Updating a deployment should not reject its own current hostname."""
        product = client.post("/api/products", json={"name": "enforce-update", "description": "test"})
        product_id = product.json()["id"]
        schema = {
            "type": "object",
            "properties": {"host": {"type": "string", "title": "hostname"}},
        }
        tmpl1 = client.post(
            f"/api/products/{product_id}/templates",
            json={"chart_ref": "oci://example/chart", "chart_version": "1.0.0", "values_schema_json": schema},
        )
        # Make it the canonical template
        client.put(f"/api/products/{product_id}", json={"template_id": tmpl1.json()["id"]})
        tmpl2 = client.post(
            f"/api/products/{product_id}/templates",
            json={"chart_ref": "oci://example/chart", "chart_version": "2.0.0", "values_schema_json": schema},
        )
        user = client.post("/api/users", json={"email": "enforce-update@example.com"})
        user_id = user.json()["id"]

        ptv_id = create_free_plan_template(db_session, product_id)

        dep = client.post(
            f"/api/users/{user_id}/deployments",
            json={"desired_template_id": tmpl1.json()["id"], "user_values_json": {"host": "same.example.com"}, "plan_template_id": ptv_id},
        )
        assert dep.status_code == 201
        dep_id = dep.json()["deployment"]["id"]

        # Mark create job done and set status to ready so update is allowed
        create_job = db_session.exec(
            select(DeploymentReconcileJobORM).where(
                DeploymentReconcileJobORM.deployment_id == UUID(dep_id),
                DeploymentReconcileJobORM.reason == "create",
            )
        ).one()
        JobService(db_session).mark_job_done(job_id=create_job.id)
        from app.models import DeploymentORM
        dep_orm = db_session.get(DeploymentORM, UUID(dep_id))
        dep_orm.status = "ready"
        db_session.add(dep_orm)
        db_session.commit()

        # Upgrade template but keep same hostname — should succeed
        resp = client.put(
            f"/api/users/{user_id}/deployments/{dep_id}",
            json={"desired_template_id": tmpl2.json()["id"], "user_values_json": {"host": "same.example.com"}},
        )
        assert resp.status_code == 200
        assert resp.json()["hostname"] == "same.example.com"
