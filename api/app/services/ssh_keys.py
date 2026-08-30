"""Account SSH public keys: validation, fingerprinting, storage.

The one implementation the API, the `caelus` CLI and any later projection
share. See openspec/changes/account-ssh-keys/design.md.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import struct
from typing import Optional

from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from sqlmodel import Session, select

from app.models import SshKeyORM, SshKeyRead
from app.services.errors import IntegrityException, NotFoundException, ValidationException


class SshKeyValidationException(ValidationException):
    """A submission this platform will not store, with a stable `code`."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class DuplicateSshKeyException(IntegrityException):
    code = "duplicate_key"


ALLOWED_KEY_TYPES = frozenset(
    {
        "ssh-ed25519",
        "ssh-rsa",
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "sk-ssh-ed25519@openssh.com",
        "sk-ecdsa-sha2-nistp256@openssh.com",
    }
)

MIN_RSA_BITS = 2048
MAX_LABEL_LENGTH = 128

_PRIVATE_KEY_MARKER = re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----", re.IGNORECASE)


def fingerprint_for_blob(blob: bytes) -> str:
    """`SHA256:<unpadded base64>`, byte-identical to `ssh-keygen -lf`."""
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _reject(code: str, message: str) -> None:
    raise SshKeyValidationException(code, message)


def _bits_for(key) -> int:
    if isinstance(key, rsa.RSAPublicKey):
        return key.key_size
    if isinstance(key, ec.EllipticCurvePublicKey):
        return key.curve.key_size
    return 256


def _algorithm_in_blob(blob: bytes) -> Optional[str]:
    """The algorithm name the wire format carries in its first string field."""
    if len(blob) < 4:
        return None
    (length,) = struct.unpack(">I", blob[:4])
    if length > len(blob) - 4 or length > 64:
        return None
    try:
        return blob[4 : 4 + length].decode("ascii")
    except UnicodeDecodeError:
        return None


class ParsedSshKey:
    """A submission that passed every check, ready to store."""

    __slots__ = ("key_type", "public_key", "fingerprint", "bits", "comment")

    def __init__(self, *, key_type: str, public_key: str, fingerprint: str, bits: int, comment: str):
        self.key_type = key_type
        self.public_key = public_key
        self.fingerprint = fingerprint
        self.bits = bits
        self.comment = comment


def parse_public_key(submission: str) -> ParsedSshKey:
    """Validate an OpenSSH public key line, or raise with a stable `code`."""
    if not submission or not submission.strip():
        _reject("malformed_key", "No key was supplied.")

    text = submission.strip()

    if _PRIVATE_KEY_MARKER.search(text) or text.startswith("-----BEGIN"):
        _reject(
            "private_key_material",
            "This is a private key. Register the public half instead \u2014 the "
            "file ending in .pub \u2014 and never share the private one.",
        )

    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        _reject(
            "multiple_keys",
            f"Submit one key at a time; this contained {len(lines)} key lines.",
        )

    fields = lines[0].split(None, 2)
    if len(fields) < 2:
        _reject(
            "malformed_key",
            "Not a valid OpenSSH public key line. Expected '<type> <base64 key> [comment]'.",
        )

    declared_type = fields[0]
    comment = fields[2].strip() if len(fields) > 2 else ""

    try:
        blob = base64.b64decode(fields[1], validate=True)
    except (binascii.Error, ValueError):
        _reject("malformed_key", "The key body is not valid base64.")

    actual_type = _algorithm_in_blob(blob)
    if actual_type is None:
        _reject("malformed_key", "The key body is not a valid SSH key blob.")

    if actual_type != declared_type:
        _reject(
            "key_type_mismatch",
            f"The key declares '{declared_type}' but its body is a "
            f"'{actual_type}' key.",
        )

    if actual_type not in ALLOWED_KEY_TYPES:
        _reject(
            "unsupported_key_type",
            f"Key type '{actual_type}' is not supported. Supported types: "
            + ", ".join(sorted(ALLOWED_KEY_TYPES))
            + ".",
        )

    canonical_blob = base64.b64encode(blob).decode("ascii")
    try:
        key = load_ssh_public_key(f"{declared_type} {canonical_blob}".encode("ascii"))
    except Exception:
        _reject(
            "malformed_key",
            f"The key body does not decode as a valid {declared_type} key.",
        )

    bits = _bits_for(key)
    if isinstance(key, rsa.RSAPublicKey) and bits < MIN_RSA_BITS:
        _reject(
            "key_too_short",
            f"RSA keys must be at least {MIN_RSA_BITS} bits; this one is {bits}.",
        )

    # Normalized from the *submitted* blob, never from the parser's
    # re-serialization: `load_ssh_public_key` strips the security-key wrapper,
    # so re-serializing an sk-* key yields a plain key with a different blob,
    # which would never authenticate.
    return ParsedSshKey(
        key_type=actual_type,
        public_key=f"{actual_type} {canonical_blob}",
        fingerprint=fingerprint_for_blob(blob),
        bits=bits,
        comment=comment,
    )


def default_label(parsed: ParsedSshKey) -> Optional[str]:
    """The key's comment, or None."""
    return parsed.comment[:MAX_LABEL_LENGTH] if parsed.comment else None


def to_read(orm: SshKeyORM) -> SshKeyRead:
    return SshKeyRead.model_validate(orm, from_attributes=True)


def list_keys(session: Session, *, user_id: int) -> list[SshKeyRead]:
    rows = session.exec(
        select(SshKeyORM)
        .where(SshKeyORM.user_id == user_id)
        .order_by(SshKeyORM.created_at, SshKeyORM.id)
    ).all()
    return [to_read(row) for row in rows]


def account_has_key(session: Session, *, user_id: int) -> bool:
    """Whether this account has any registered key at all."""
    return (
        session.exec(select(SshKeyORM.id).where(SshKeyORM.user_id == user_id).limit(1)).first()
        is not None
    )


def get_key(session: Session, *, user_id: int, fingerprint: str) -> SshKeyORM:
    row = session.exec(
        select(SshKeyORM).where(
            SshKeyORM.user_id == user_id,
            SshKeyORM.fingerprint == fingerprint,
        )
    ).one_or_none()
    if row is None:
        raise NotFoundException(f"No SSH key with fingerprint {fingerprint}")
    return row


def add_key(
    session: Session,
    *,
    user_id: int,
    public_key: str,
    label: Optional[str] = None,
) -> SshKeyRead:
    parsed = parse_public_key(public_key)

    existing = session.exec(
        select(SshKeyORM).where(
            SshKeyORM.user_id == user_id,
            SshKeyORM.fingerprint == parsed.fingerprint,
        )
    ).one_or_none()
    if existing is not None:
        raise DuplicateSshKeyException(
            f"This key is already registered as '{existing.label}' "
            f"({existing.fingerprint})."
            if existing.label
            else f"This key is already registered ({existing.fingerprint})."
        )

    chosen = (label or "").strip() or default_label(parsed)
    if chosen is not None and len(chosen) > MAX_LABEL_LENGTH:
        _reject(
            "malformed_key",
            f"Label must be at most {MAX_LABEL_LENGTH} characters.",
        )

    row = SshKeyORM(
        user_id=user_id,
        key_type=parsed.key_type,
        public_key=parsed.public_key,
        fingerprint=parsed.fingerprint,
        bits=parsed.bits,
        label=chosen,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return to_read(row)


def delete_key(session: Session, *, user_id: int, fingerprint: str) -> None:
    """Remove a key outright, or raise if the account does not hold it."""
    row = get_key(session, user_id=user_id, fingerprint=fingerprint)
    session.delete(row)
    session.commit()
