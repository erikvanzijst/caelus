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
    # tf/deps/certmanager and tf/deps/system/traefik.tf)
    tls_cluster_issuer: str = "letsencrypt-http"

    # ── Tenant network isolation ──────────────────────────────────────────
    # Cluster-specific inputs to the baseline NetworkPolicy + Pod Security labels
    # the reconciler (and `sync-network-policies`) apply to every tenant namespace.
    # Defaults match the current cluster: Traefik in kube-system, the shared SMTP
    # relay (app=smtp:25) in the `mailer` namespace, and the k3s CoreDNS ClusterIP.
    tenant_netpol_name: str = "caelus-tenant-baseline"
    ingress_namespace: str = "kube-system"
    ingress_pod_label: str = "traefik"
    mailer_namespace: str = "mailer"
    mailer_pod_label: str = "smtp"
    mailer_port: int = 25
    dns_cluster_ip: str = "10.43.0.10"
    tenant_egress_except_cidrs: list[str] = [
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
    ]
    # SFTP router (sshpiper) admitted into tenant namespaces on the sidecar
    # port only. Per-environment: the dev instance must point at its own
    # router namespace (sshpiper-dev) so the environments cannot cross-route
    # even though both routers watch Pipes cluster-wide.
    sshpiper_namespace: str = "sshpiper"
    sshpiper_pod_label: str = "sshpiper"
    sftp_sidecar_port: int = 2222

    # User-facing SFTP endpoint shown in the UI/API. These are the public
    # router values, NOT the internal HAProxy/cluster ports (2222/2223):
    # prod freepod.eu:22, dev dev.freepod.eu:23. Set per environment.
    sftp_host: str = "freepod.eu"
    sftp_port: int = 22

    mollie_api_key: str | None = None
    mollie_redirect_url: str | None = None
    mollie_webhook_base_url: str | None = None

    # ── Google Photos → Immich migration SPIKE (drive.file + Picker) ──────
    # Client ID is non-secret (also handed to the browser via VITE_GOOGLE_*);
    # the client secret stays server-side only, used for the code->token and
    # refresh_token->access_token exchanges.
    google_client_id: str
    google_client_secret: str


@lru_cache
def get_settings() -> CaelusSettings:
    return CaelusSettings()


def get_static_url_base() -> str:
    """Get the base URL for static file serving."""
    return "/api/static"
