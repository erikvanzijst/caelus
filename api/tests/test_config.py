import os

import pytest
from app.config import CaelusSettings


def test_default_values(monkeypatch):
    # Remove any CAELUS_* env vars so we test true defaults
    for key in list(os.environ):
        if key.startswith("CAELUS_"):
            monkeypatch.delenv(key)
    settings = CaelusSettings(
        _env_file=None,
    )
    assert settings.database_url == "postgresql+psycopg://caelus:caelus@localhost:5432/caelus"
    assert settings.log_level == "INFO"
    assert settings.lb_ips == []
    assert settings.wildcard_domains == []
    assert settings.reserved_hostnames == []


def test_env_var_loading(monkeypatch):
    monkeypatch.setenv("CAELUS_DATABASE_URL", "sqlite:///test.db")
    monkeypatch.setenv("CAELUS_LOG_LEVEL", "DEBUG")
    settings = CaelusSettings(_env_file=None)
    assert settings.database_url == "sqlite:///test.db"
    assert settings.log_level == "DEBUG"


def test_list_field_json_parsing(monkeypatch):
    monkeypatch.setenv("CAELUS_LB_IPS", '["1.2.3.4","2001:db8::1"]')
    monkeypatch.setenv("CAELUS_WILDCARD_DOMAINS", '["app.deprutser.be","apps.example.com"]')
    monkeypatch.setenv("CAELUS_RESERVED_HOSTNAMES", '["smtp.app.deprutser.be"]')
    settings = CaelusSettings(_env_file=None)
    assert settings.lb_ips == ["1.2.3.4", "2001:db8::1"]
    assert settings.wildcard_domains == ["app.deprutser.be", "apps.example.com"]
    assert settings.reserved_hostnames == ["smtp.app.deprutser.be"]


def test_static_path_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CAELUS_STATIC_PATH", str(tmp_path))
    settings = CaelusSettings(_env_file=None)
    assert settings.static_path == tmp_path


def test_legacy_database_url_not_read(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://old-host/old-db")
    monkeypatch.delenv("CAELUS_DATABASE_URL", raising=False)
    settings = CaelusSettings(_env_file=None)
    assert settings.database_url == "postgresql+psycopg://caelus:caelus@localhost:5432/caelus"


def test_get_settings_is_cached():
    from app.config import get_settings

    get_settings.cache_clear()
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
    get_settings.cache_clear()
