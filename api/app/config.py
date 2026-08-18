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

    # ── Per-deployment object storage ─────────────────────────────────────
    # The API provisions a private bucket and access key for every deployment
    # whose product template opts in, so it holds a Garage admin credential.
    garage_admin_url: str = ""
    garage_admin_token: str = ""

    # Companion to the plan's byte allowance, which Garage requires to be set
    # alongside it — one cannot be changed without the other.
    deployment_bucket_max_objects: int = 1_000_000

    # Applied to a deleted deployment's bucket so Garage reclaims the objects on
    # its own.
    deployment_bucket_expiry_days: int = 1

    # ── Deployment logs (Loki) ────────────────────────────────────────────
    loki_base_url: str = ""
    loki_query_timeout_seconds: float = 30.0
    # How many trailing lines a log read starts with. A long-running
    # application's whole history is not spooled to a caller who asked to watch
    # what is happening now.
    log_tail_lines: int = 200
    # Ceiling on what a caller may ask for, and also the batch size the follow
    # loop requests. Bounding both matters: the API is a single worker process.
    log_max_tail_lines: int = 5000

    # How far back the *first* read looks. Loki's own default window for
    # `query_range` is one hour, which would silently return nothing for an
    # application that has been quiet longer than that -- the exact case a
    # reader is usually investigating. Sized to the store's retention: looking
    # further back cannot find anything.
    log_initial_lookback_seconds: int = 14 * 24 * 3600

    # How often the follow loop re-queries the store. Trades latency against
    # load on a single-replica Loki.
    log_poll_interval_seconds: float = 2.0

    # Keepalive interval for an open follow stream, as an SSE comment.
    #
    # MUST stay below the shortest connection timeout anywhere in the path,
    # which is NOT a property of this repository: the platform edge is
    # `client -> homelab HAProxy -> k3s Traefik -> API`, and HAProxy's
    # `timeout client` / `timeout server` are operator-configured and commonly
    # 30-60s. Configurable for exactly that reason. Re-measure against the live
    # edge before raising it.
    log_keepalive_seconds: int = 10

    # Hard cap on how long one log stream may stay open, measured from when it
    # opened -- **not** from its last line.
    # It is to trigger periodic re-authorization.
    # Costs the user nothing: the stream ends with an `end` event carrying a
    # reason, and `freepod log -f` resumes from its cursor inclusively, so no
    # line is lost and no gap appears.
    log_stream_max_lifetime_seconds: int = 3600

    # How many of a failed release's own log lines get attached to the
    # deployment's `last_error`, so `freepod deploy` can report *why* the
    # application refused to start without a second command.
    log_failure_tail_lines: int = 50

    # How many concurrent log streams one user may hold. The API runs
    # `--workers 1` and serves every other endpoint from a bounded thread pool,
    # so an unbounded number of long-lived streams would deny service to every
    # endpoint, not just this one.
    log_max_streams_per_user: int = 3

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
