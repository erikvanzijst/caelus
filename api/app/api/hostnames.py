from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.services.errors import HostnameException
from app.services.hostnames import require_valid_hostname_for_deployment

router = APIRouter(tags=["hostnames"])


class HostnameCheck(BaseModel):
    """Result of validating a candidate hostname for a deployment.

    Fields:
    - ``fqdn``: the fully-qualified domain name that was checked, normalized to
      lowercase (echoed back so the caller sees the canonical form).
    - ``usable``: ``True`` when the name passed every validation check and can
      be used for a deployment; ``False`` otherwise.
    - ``reason``: ``None`` when ``usable`` is ``True``. When ``usable`` is
      ``False`` this is a short machine-readable code explaining the rejection,
      one of: ``invalid`` (malformed name), ``nested_subdomain`` (more than one
      label under a platform wildcard domain), ``reserved`` (reserved by the
      platform), ``in_use`` (already in use by another deployment), or
      ``not_resolving`` (no CNAME record pointing at the platform CNAME target).
    """

    fqdn: str
    usable: bool
    reason: str | None = None


@router.get(
    "/hostnames/{fqdn}",
    response_model=HostnameCheck,
    summary="Check whether a hostname is usable for a deployment",
    response_description=(
        "A HostnameCheck: the normalized `fqdn`, a `usable` boolean, and a "
        "human-readable `reason` code when `usable` is false."
    ),
    responses={
        200: {
            "description": (
                "Always 200. `usable=true` with `reason=null` for accepted "
                "names; `usable=false` with a `reason` code for rejected names. "
                "Rejections are never surfaced as an error status."
            )
        }
    },
)
def check_hostname(
    fqdn: str = Path(
        ...,
        description=(
            "Fully-qualified domain name to validate. Lowercased server-side "
            "before any checks run and echoed back normalized in the response."
        ),
    ),
    # Intentionally unauthenticated: the response (usable/reason) carries nothing
    # sensitive and the field validates hostnames as the user types, before any
    # deployment exists. See `list_domains` below, which is public for the same
    # reason.
    #
    # Note: validation performs outbound DNS lookups to caller-controlled
    # authoritative nameservers (see _check_cname), each able to hold a worker
    # for up to the resolver lifetime. Being unauthenticated, this is in
    # principle a DoS / DNS-amplification handle. Accepted as low risk: the cost
    # per request is small, and the same vector is reachable by any authenticated
    # user anyway, so auth was never a real mitigation. Add a per-IP rate limit
    # here if abuse ever materializes.
    session: Session = Depends(get_session),
) -> HostnameCheck:
    """Validate a candidate hostname and report whether it can be used for a
    deployment, without creating or reserving anything.

    ## Authorization
    Public — no authentication required.

    ## Parameters
    - `fqdn` (path): the hostname to validate. Normalized to lowercase; the
      normalized form is echoed back in the response.

    ## Behavior
    Runs the full set of hostname checks and stops at the first failure. On
    success the response is `usable=true` with `reason=null`. On failure the
    response is `usable=false` with a machine-readable `reason` code; a rejected
    name is never returned as an error status:
    - `invalid` — malformed name (too long, bad labels, or fewer than two
      labels).
    - `nested_subdomain` — more than one label placed under a platform wildcard
      domain (only a single label is allowed there).
    - `reserved` — the name is reserved by the platform.
    - `in_use` — the hostname is already in use by another deployment.
    - `not_resolving` — the hostname has no CNAME record pointing at the
      platform CNAME target (see `GET /cname-target`). Not applicable to
      subdomains of a platform wildcard domain, or when no platform domain is
      configured.

    ## Errors
    Always returns **200**. Rejected names are reported in the body via
    `usable=false` and a `reason` code; no 4xx status is returned.
    """
    fqdn = fqdn.lower()
    try:
        require_valid_hostname_for_deployment(session, fqdn)
        return HostnameCheck(fqdn=fqdn, usable=True)
    except HostnameException as exc:
        return HostnameCheck(fqdn=fqdn, usable=False, reason=exc.reason)


@router.get(
    "/domains",
    response_model=list[str],
    summary="List the platform-provided wildcard domains",
    response_description="JSON array of configured wildcard domain suffixes (empty when none are configured).",
    responses={200: {"description": "The configured wildcard domain suffixes, e.g. `[\"freepod.eu\"]`."}},
)
def list_domains() -> list[str]:
    """List the platform-provided wildcard domain suffixes.

    A deployment can use a single-label subdomain under any of these domains
    (e.g. `myapp.freepod.eu`) without configuring any DNS of your own.

    ## Authorization
    Public — no authentication required.

    ## Behavior
    Returns the configured wildcard domain suffixes, or an empty array when
    none are configured.

    ## Errors
    - Always **200**.
    """
    return get_settings().wildcard_domains


@router.get(
    "/cname-target",
    response_model=str,
    summary="Get the platform domain custom hostnames must CNAME to",
    response_description="The platform CNAME target domain as a JSON string (empty string when unconfigured).",
    responses={200: {"description": "The CNAME target, e.g. `\"dev.freepod.eu\"`, or `\"\"` when no domain is configured."}},
)
def cname_target() -> str:
    """Return the platform domain that custom hostnames must point to.

    To use your own domain with a deployment, create a CNAME record for it
    whose target is exactly this value. The hostname check
    (`GET /hostnames/{fqdn}`) verifies that this record exists.

    ## Authorization
    Public — no authentication required.

    ## Behavior
    Returns the CNAME target domain. Returns an
    empty string when no platform domain is configured, in which case custom
    hostnames are not subject to the CNAME check.

    ## Errors
    - Always **200**.
    """
    return get_settings().domain
