from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CaelusSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAELUS_", env_file=(".env", ".env.local"))

    base_url: str = "http://localhost:5173"
    base_url_api: str = "http://localhost:8000/api"
    database_url: str = "postgresql+psycopg://caelus:caelus@localhost:5432/caelus"
    static_path: Path = Path(__file__).parent.parent / "static"
    log_level: str = "INFO"

    domain: str = ""
    wildcard_domains: list[str] = []
    reserved_hostnames: list[str] = []

    # cert-manager ClusterIssuer used for per-app HTTP-01 certs on custom domains.
    # Override to a `-staging` issuer during rollout. `*.freepod.eu` apps do not use
    # this — they are served Traefik's default wildcard cert store.
    # (The ACME account email and the wildcard secret name are Terraform-side: see
    # tf/deps/certmanager and tf/deps/system/traefik.tf — not API concerns.)
    tls_cluster_issuer: str = "letsencrypt-http"

    mollie_api_key: str | None = None
    mollie_redirect_url: str | None = None
    mollie_webhook_base_url: str | None = None


@lru_cache
def get_settings() -> CaelusSettings:
    return CaelusSettings()


def get_static_url_base() -> str:
    """Get the base URL for static file serving."""
    return "/api/static"
