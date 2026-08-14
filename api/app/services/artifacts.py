"""Project-archive upload slots on the object store.

Uploads go straight from the client to Garage; the API never sees the bytes. It
only mints the credential, and the credential is what carries the platform's
two constraints — *where* the object may be written and *how large* it may be.

Nothing here is persisted. An upload that is never started, never finishes, or
is abandoned leaves no row to reconcile: the object (or the incomplete
multipart upload) is reclaimed by the bucket's own lifecycle rules.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.config import CaelusSettings, get_settings
from app.services.errors import CaelusException, ValidationException

logger = logging.getLogger(__name__)

# An artifact id is a uuid4 in hex — 32 lowercase hex characters, nothing else.
#
# The key is composed server-side from the caller's id and this value, which is
# what binds an artifact to its uploader (design D7). That argument only holds
# while the id cannot contain a separator: `artifact_id` *is* client-supplied
# when a build is created, so an unconstrained value such as "../7/theirs"
# would compose a key outside the caller's own prefix. Pinning the alphabet is
# what removes the check rather than hardening it — a traversal sequence,
# percent-encoded or not, simply is not a well-formed artifact id.
ARTIFACT_ID_RE = re.compile(r"^[0-9a-f]{32}$")

ARTIFACT_KEY_PREFIX = "artifacts"
ARTIFACT_KEY_SUFFIX = ".tgz"


class ArtifactUploadSlot(BaseModel):
    """A minted upload slot: where to POST, and what to POST with.

    `fields` are the presigned POST's policy fields and must be sent verbatim
    as multipart form fields, with the file part last — the object store
    validates the signed policy, so a client that reorders or edits them gets a
    rejection rather than a differently-shaped upload.
    """

    artifact_id: str
    url: str
    fields: dict[str, str]
    # Echoed so a client can refuse an oversized archive before spending the
    # upload rather than after; the store enforces it regardless.
    max_bytes: int
    expires_in: int


@lru_cache
def get_s3_client() -> BaseClient:
    """The S3 client for the configured object store.

    Cached: constructing a boto3 client parses service models and costs real
    milliseconds, which is not something to pay per request. Tests replace this
    function wholesale rather than reaching into the cache.
    """
    settings = get_settings()
    missing = [
        name
        for name in ("s3_endpoint_url", "s3_bucket", "s3_access_key_id", "s3_secret_access_key")
        if not getattr(settings, name)
    ]
    if missing:
        raise CaelusException(
            "object store is not configured: missing " + ", ".join(sorted(missing))
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
    )


def validate_artifact_id(artifact_id: str) -> str:
    """Return `artifact_id` if it is well-formed, else raise.

    Raises ``ValidationException`` (a 400), which is also the answer for an id
    crafted to resolve outside the caller's prefix.
    """
    if not isinstance(artifact_id, str) or not ARTIFACT_ID_RE.match(artifact_id):
        raise ValidationException("artifact_id must be 32 lowercase hexadecimal characters")
    return artifact_id


def artifact_key(user_id: int, artifact_id: str) -> str:
    """The object key for one user's artifact.

    Composed from the authenticated caller's id and a validated artifact id, so
    an artifact is bound to its uploader by construction. No caller-supplied
    key, path, or URL is ever an input to this.
    """
    return f"{ARTIFACT_KEY_PREFIX}/{int(user_id)}/{validate_artifact_id(artifact_id)}{ARTIFACT_KEY_SUFFIX}"


def mint_upload_slot(
    user_id: int,
    *,
    settings: CaelusSettings | None = None,
) -> ArtifactUploadSlot:
    """Issue an upload slot for a new artifact belonging to `user_id`.

    A presigned **POST**, not a PUT: only POST carries a policy document, and
    only a policy can express `content-length-range`. That is what puts the
    size cap at the object store rather than in a client that may ignore it or
    a proxy body limit that is easy to misconfigure and invisible when absent.
    """
    settings = settings or get_settings()
    artifact_id = uuid4().hex
    key = artifact_key(user_id, artifact_id)

    # boto3 adds an exact-match `{"key": key}` condition of its own because the
    # key carries no `${filename}` placeholder — that is what makes a write to
    # any other key fail the policy. Do not add a `starts-with` key condition
    # here; it would replace the exact match and widen the grant to a prefix.
    presigned = get_s3_client().generate_presigned_post(
        Bucket=settings.s3_bucket,
        Key=key,
        Conditions=[["content-length-range", 1, settings.artifact_max_bytes]],
        ExpiresIn=settings.s3_presigned_url_expiry_seconds,
    )

    logger.info(
        "Minted artifact upload slot user_id=%s artifact_id=%s max_bytes=%s ttl=%s",
        user_id,
        artifact_id,
        settings.artifact_max_bytes,
        settings.s3_presigned_url_expiry_seconds,
    )
    return ArtifactUploadSlot(
        artifact_id=artifact_id,
        url=presigned["url"],
        fields=presigned["fields"],
        max_bytes=settings.artifact_max_bytes,
        expires_in=settings.s3_presigned_url_expiry_seconds,
    )


def artifact_download_url(
    user_id: int,
    artifact_id: str,
    *,
    settings: CaelusSettings | None = None,
) -> str:
    """A presigned GET for one user's artifact, for the build container to fetch.

    This is the *only* credential a build pod ever receives: it grants read on
    exactly one object and expires. The build container runs tenant-supplied
    code, so anything longer-lived or broader here would be a credential handed
    to every tenant.

    The clock starts when the Job is created, not when the build was queued, so
    the expiry only has to cover pod scheduling, the image pull, and the fetch.
    """
    settings = settings or get_settings()
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": artifact_key(user_id, artifact_id)},
        ExpiresIn=settings.s3_presigned_url_expiry_seconds,
    )


def artifact_exists(
    user_id: int,
    artifact_id: str,
    *,
    settings: CaelusSettings | None = None,
) -> bool:
    """Whether `user_id`'s artifact is actually present in the object store.

    Used by build creation so that an upload which silently failed surfaces at
    the point the client can still act on it, rather than minutes later as an
    obscure fetch error inside a build container.

    Because the key is derived from the caller, this answers "does *your*
    artifact exist" — another user's artifact is simply absent at the key this
    builds, with no separate ownership check to get wrong.
    """
    settings = settings or get_settings()
    key = artifact_key(user_id, artifact_id)
    try:
        get_s3_client().head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status in (403, 404):
            # 403 is what a bucket that hides existence returns instead of 404;
            # either way the artifact is not usable, and treating them alike
            # avoids leaking which one it was.
            return False
        raise
    return True
