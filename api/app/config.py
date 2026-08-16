from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class CaelusSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAELUS_", env_file=(".env", ".env.local"))

    base_url: str = "http://localhost:5173"
    base_url_api: str = "http://localhost:8000/api"

    # Current Terms of Service version (the ToS markdown's effective date). This
    # is a *release* constant, not per-environment config: it must match the ToS
    # document bundled in the same image, which is identical in dev and prod. It
    # is intentionally NOT set in .env/Terraform — a code default gives dev/prod
    # parity by construction, and a CI test binds it to the ToS markdown so the
    # two cannot drift. The CAELUS_CURRENT_TOS_VERSION override exists only as an
    # emergency escape hatch and is not populated in normal operation.
    current_tos_version: str = "2026-07-01"

    database_url: str = "postgresql+psycopg://caelus:caelus@localhost:5432/caelus"
    static_path: Path = Path(__file__).parent.parent / "static"
    log_level: str = "INFO"

    # Desired state for curated products, baked into the API image and applied
    # by the `catalog` init container. The default points at the checkout so the
    # CLI works from a dev tree without configuration.
    catalog_dir: Path = Path(__file__).parent.parent.parent / "products" / "catalog"

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
    sshpiper_namespace: str = "sshpiper"
    sshpiper_pod_label: str = "sshpiper"
    sftp_sidecar_port: int = 2222
    sftp_host: str = "freepod.eu"
    sftp_port: int = 22

    # ── Reconcile job lease ───────────────────────────────────────────────
    # How long a worker may hold a claimed reconcile job before another worker
    # is allowed to steal it. A worker that dies mid-reconcile (pod restart,
    # OOM kill, node eviction) leaves its job stranded at status='running' with
    # locked_by pointing at a process that will never come back; without a
    # lease the job is never retried and its deployment sits in
    # provisioning/deleting forever.
    #
    # Do NOT tune this below HELM_TIMEOUT_SEC (300s, see
    # app/services/reconcile.py): a single reconcile may legitimately spend the
    # full Helm wall-clock budget on `helm upgrade --install --wait`, and a
    # lease shorter than that would let a second worker steal the job out from
    # under a live, healthy one. 600s leaves ~2x margin.
    reconcile_job_lease_seconds: int = 600

    # ── Object store (Garage, S3-compatible) ──────────────────────────────
    s3_endpoint_url: str = ""
    s3_region: str = "garage"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_presigned_url_expiry_seconds: int = 900

    # ── Builds ────────────────────────────────────────────────────────────
    # The builder image is published by hand (see products/custom/builder/),
    # not by the API's own CI, so it is versioned independently of the API
    # image and supplied by Terraform rather than pinned here — no version
    # literal in this file means none to drift.
    #
    # Empty is not a usable value; it is what everything that is not a build
    # worker gets away with. Nothing else reads this, so requiring it would
    # only mean alembic, the tests and the local CLI could not construct
    # settings at all. `build_job_manifest` rejects the empty string, which
    # puts the failure on the one path that actually needs the image.
    builder_image: str = ""

    # Namespace the per-build Jobs run in. Deliberately neither the platform
    # namespace nor a tenant one: build pods execute untrusted tenant code and
    # get their own Pod Security Admission labels, ServiceAccount, and
    # NetworkPolicy, none of which should be shared with anything else.
    builds_namespace: str = "caelus-builds"
    build_registry_host: str = "registry.home"

    # Largest project archive accepted, enforced by Garage itself through the
    # presigned POST policy's content-length-range rather than by the client or
    # a proxy body limit.
    artifact_max_bytes: int = 100 * 1024 * 1024
    build_log_max_bytes: int = 10 * 1024 * 1024

    # Wall-clock budget for a single build, applied as the Job's
    # activeDeadlineSeconds so Kubernetes.
    build_deadline_seconds: int = 3600

    # How far past the deadline the worker waits before deleting the Job
    # itself. This is a backstop for Kubernetes having failed to enforce its
    # own deadline.
    build_deadline_grace_seconds: int = 300

    # How many builds may be running at once. Concurrency is this number, not
    # the worker's process count — one worker advances every running build per
    # pass without blocking on any of them.
    build_max_in_flight: int = 1

    # Sleep between worker passes.
    build_worker_interval_seconds: float = 1

    mollie_api_key: str | None = None
    mollie_redirect_url: str | None = None
    mollie_webhook_base_url: str | None = None


@lru_cache
def get_settings() -> CaelusSettings:
    return CaelusSettings()


def get_static_url_base() -> str:
    """Get the base URL for static file serving."""
    return "/api/static"
