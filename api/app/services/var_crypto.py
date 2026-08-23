"""Encryption of deployment var values under a rotatable Fernet keyring.

Every var value is encrypted, including the ones not marked sensitive: one
column, one code path, no per-row branch on where the plaintext lives.

Each row records the *fingerprint* of the key that encrypted it -- the first
4 bytes of ``sha256`` over the decoded key material, as lowercase hex -- and
never a position in the configured list. Rotation introduces a key by
prepending, so a positional identifier would silently come to name a
different key on every historical row: an identifier destroyed by the one
operation it exists to support.

``MultiFernet`` is deliberately not used. Its try-every-key decryption exists
to work around a token that carries no key identifier; once a row carries one,
a direct lookup is O(1) and fails with something actionable -- naming the
fingerprint that is missing -- rather than an undifferentiated ``InvalidToken``
that cannot tell a retired key from a corrupted row.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Callable

from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from app.config import get_settings
from app.models.core import DeploymentVarORM, ProductTemplateVersionORM
from app.services.errors import CaelusException
from app.services.template_values import schema_declares_vars

KEY_ID_BYTES = 4
KEY_ID_LEN = KEY_ID_BYTES * 2


class VarEncryptionException(CaelusException):
    """The keyring cannot serve a value it was asked to encrypt or decrypt."""


def key_fingerprint(key: str) -> str:
    """Fingerprint a Fernet key: sha256 over its *material*, not its encoding.

    Whitespace around a key pasted into a Secret is stripped by the settings
    parser, so two spellings of one key cannot fingerprint differently.
    """
    try:
        material = base64.urlsafe_b64decode(key)
    except Exception as exc:  # noqa: BLE001 - binascii raises several types
        raise VarEncryptionException(f"not a valid Fernet key: {exc}") from exc
    return hashlib.sha256(material).hexdigest()[:KEY_ID_LEN]


class Keyring:
    """An ordered list of Fernet keys: the first encrypts, all of them decrypt."""

    def __init__(self, keys: list[str]):
        self._fernets: dict[str, Fernet] = {}
        self._order: list[str] = []
        for key in keys:
            fingerprint = key_fingerprint(key)
            try:
                fernet = Fernet(key)
            except Exception as exc:  # noqa: BLE001 - cryptography raises ValueError
                raise VarEncryptionException(f"not a valid Fernet key: {exc}") from exc
            if fingerprint in self._fernets:
                # Not merely tolerated as a duplicate: two *different* keys can
                # collide here too, and that ambiguity has to surface. The
                # startup check (verify_keyring) is what turns it fatal.
                raise VarEncryptionException(
                    f"two configured keys share the fingerprint {fingerprint}"
                )
            self._fernets[fingerprint] = fernet
            self._order.append(fingerprint)

    def __bool__(self) -> bool:
        return bool(self._order)

    @property
    def key_ids(self) -> list[str]:
        """Configured fingerprints, newest first."""
        return list(self._order)

    def current_key_id(self) -> str:
        if not self._order:
            raise VarEncryptionException(
                "no encryption key is configured (CAELUS_VAR_ENCRYPTION_KEYS is empty)"
            )
        return self._order[0]

    def encrypt(self, plaintext: str) -> tuple[str, str]:
        """Encrypt under the current key, returning ``(ciphertext, key_id)``."""
        key_id = self.current_key_id()
        token = self._fernets[key_id].encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii"), key_id

    def decrypt(self, ciphertext: str, key_id: str) -> str:
        fernet = self._fernets.get(key_id)
        if fernet is None:
            raise VarEncryptionException(
                f"value was encrypted with key {key_id}, which is not configured"
            )
        try:
            return fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise VarEncryptionException(
                f"value naming key {key_id} could not be decrypted with it"
            ) from exc


@lru_cache
def get_keyring() -> Keyring:
    return Keyring(get_settings().var_encryption_keys)


def current_key_id() -> str:
    return get_keyring().current_key_id()


def encrypt(plaintext: str) -> tuple[str, str]:
    return get_keyring().encrypt(plaintext)


def decrypt(ciphertext: str, key_id: str) -> str:
    return get_keyring().decrypt(ciphertext, key_id)


def verify_keyring(session: Session) -> None:
    """Verify this process can serve the vars already in storage.

    Every failure here is fatal rather than a warning. A row whose key is no
    longer configured can never be decrypted again, and that has to surface in
    front of whoever edited the key list -- not months later, inside a tenant's
    failed rollout, with the release row already written.
    """
    settings = get_settings()
    # A fingerprint collision between two configured keys raises here: it makes
    # `key_id` ambiguous, so nothing downstream can be trusted.
    keyring = Keyring(settings.var_encryption_keys)

    if not keyring:
        declaring = [
            t.id
            for t in session.exec(
                select(ProductTemplateVersionORM).where(
                    ProductTemplateVersionORM.deleted_at.is_(None)  # type: ignore[union-attr]
                )
            ).all()
            if schema_declares_vars(t.values_schema_json)
        ]
        if declaring:
            raise VarEncryptionException(
                "no encryption key is configured (CAELUS_VAR_ENCRYPTION_KEYS is empty) "
                f"while product template(s) {declaring} declare vars"
            )

    stored = {
        key_id
        for key_id in session.exec(
            select(DeploymentVarORM.key_id).where(
                DeploymentVarORM.key_id.is_not(None)  # type: ignore[union-attr]
            )
        ).all()
        if key_id is not None
    }
    missing = sorted(stored - set(keyring.key_ids))
    if missing:
        raise VarEncryptionException(
            "stored deployment vars name encryption key(s) that are not configured: "
            + ", ".join(missing)
        )


def rotate_vars(
    session: Session,
    *,
    batch_size: int = 200,
    on_batch: Callable[[int], None] | None = None,
) -> int:
    """Re-encrypt every row not already under the current key.

    Each batch is committed on its own, which is what makes the sweep
    resumable and safe to interrupt: a row names the key that encrypted it, so
    a half-swept table is fully readable and a re-run simply picks up the rows
    that are left. Tombstones carry no value and are skipped by the filter.

    Returns the number of rows re-encrypted.
    """
    if batch_size < 1:
        raise VarEncryptionException("batch_size must be >= 1")
    keyring = get_keyring()
    current = keyring.current_key_id()
    rotated = 0
    while True:
        rows = session.exec(
            select(DeploymentVarORM)
            .where(
                DeploymentVarORM.key_id.is_not(None),  # type: ignore[union-attr]
                DeploymentVarORM.key_id != current,
            )
            .order_by(DeploymentVarORM.id)  # type: ignore[arg-type]
            .limit(batch_size)
        ).all()
        if not rows:
            return rotated
        for row in rows:
            assert row.value_encrypted is not None and row.key_id is not None
            plaintext = keyring.decrypt(row.value_encrypted, row.key_id)
            row.value_encrypted, row.key_id = keyring.encrypt(plaintext)
            session.add(row)
        session.commit()
        rotated += len(rows)
        if on_batch is not None:
            on_batch(rotated)
