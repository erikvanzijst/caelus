from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.models import SshEdgeRead

router = APIRouter(tags=["ssh"])


def _host_key_dict(openssh_public_key: str) -> dict[str, str]:
    """Split an OpenSSH public key line into ``{key type: base64 body}``.

    ``ssh-ed25519 AAAA… [comment]`` becomes ``{"ssh-ed25519": "AAAA…"}``. An
    empty or malformed value yields an empty mapping, which a client treats as
    "nothing to verify against" -- never as "trust on first use".
    """
    parts = openssh_public_key.strip().split()
    if len(parts) >= 2:
        return {parts[0]: parts[1]}
    return {}


@router.get(
    "/ssh",
    response_model=SshEdgeRead,
    summary="Get the SSH edge's address and host key",
    response_description=(
        "The edge's host, port, and host public key keyed by OpenSSH key type."
    ),
    responses={
        200: {"description": "The edge's address and host key for this environment."},
    },
)
def get_ssh_edge() -> SshEdgeRead:
    """Return how to reach this environment's SSH edge, and how to verify it.

    ## Behavior
    `host` and `port` are the user-facing edge values from per-environment
    configuration, the same ones the SFTP credentials endpoint reports.
    `host_key` carries the edge's host public key, keyed by OpenSSH key type,
    so a client can pin it in its own known_hosts rather than trusting whatever
    answers on first use. An environment that has not configured the key reports
    an empty `host_key`; a client must treat that as "cannot verify" and refuse,
    never as "trust on first use".
    """
    settings = get_settings()
    return SshEdgeRead(
        host_key=_host_key_dict(settings.ssh_edge_host_public_key),
        host=settings.sftp_host,
        port=settings.sftp_port,
    )
