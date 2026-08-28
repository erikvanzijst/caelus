from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_user, require_self
from app.models import SshKeyCreate, SshKeyRead, UserORM
from app.services import ssh_keys as ssh_key_service

router = APIRouter(prefix="/users/{user_id}/ssh-keys", tags=["ssh-keys"])

FINGERPRINT_DESCRIPTION = (
    "The key's `SHA256:` fingerprint, as `ssh-keygen -lf` reports it. Matched "
    "as a path-converter segment because roughly half of all fingerprints "
    "contain a `/`."
)


@router.get(
    "",
    response_model=list[SshKeyRead],
    summary="List an account's SSH public keys",
    response_description="The account's registered keys, oldest first.",
    responses={
        200: {"description": "The account's keys; an empty array if it holds none."},
        403: {"description": "Caller may only read their own keys."},
        404: {"description": "The request carried no authenticated identity."},
    },
)
def list_ssh_keys(
    user_id: int = Path(..., description="ID of the account whose keys are listed."),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> list[SshKeyRead]:
    """List the SSH public keys registered on an account.

    ## Authorization
    You may list your own keys; administrators may list any account's. Other
    requests receive `403 Forbidden`.

    ## Behavior
    A plain array, empty when the account holds no keys — never a `404`. Each
    entry carries the fingerprint, key type, size in bits, label, the
    normalized public key body and when it was registered. No response on any
    path contains private key material; none is ever stored.

    Registering a key currently grants no access: nothing reads these keys
    yet, and SSH still authenticates with per-deployment passwords.

    ## Errors
    - **403 Forbidden** — listing another account's keys without administrator
      privileges.
    """
    return ssh_key_service.list_keys(session, user_id=user_id)


@router.post(
    "",
    response_model=SshKeyRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register an SSH public key",
    response_description="The stored key, including its computed fingerprint. "
    "`Location` carries its URL.",
    responses={
        201: {"description": "The key was registered."},
        400: {
            "description": "The submission was refused. The body's `code` names "
            "which check failed: `malformed_key`, `private_key_material`, "
            "`multiple_keys`, `unsupported_key_type`, `key_type_mismatch` or "
            "`key_too_short`."
        },
        403: {"description": "Keys may only be added to your own account."},
        409: {"description": "This key is already registered (`code`: `duplicate_key`)."},
        422: {"description": "The body carried a field other than `public_key` or `label`."},
    },
)
def add_ssh_key(
    payload: SshKeyCreate,
    response: Response,
    user_id: int = Path(..., description="ID of the account to register the key on."),
    current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SshKeyRead:
    """Register an SSH public key on an account.

    ## Authorization
    **The owner only** — unlike read and delete, an administrator may *not*
    add a key to another account. Installing a key on someone's account
    creates a credential that authenticates as them, which is impersonation
    rather than administration. Administrative reach over this collection
    exists so a compromised key can be revoked, not so one can be granted.

    ## Parameters
    - **public_key** — one public key in OpenSSH `authorized_keys` format,
      `<type> <base64 blob> [comment]`.
    - **label** — optional; defaults to the key's trailing comment, or to a
      generated label when it carries none.

    ## Behavior
    The fingerprint and key type are derived from the key material and are
    never accepted from a client: a body supplying either is rejected with
    **422** rather than accepted with the field ignored.

    The stored key body is normalized to `<type> <blob>` with the comment
    stripped — the comment has already been consumed as the default label.

    Accepted types are Ed25519, ECDSA over NIST P-256/384/521, RSA of at least
    2048 bits, and the FIDO security-key variants of Ed25519 and ECDSA.
    `ssh-dss` is refused. The key type is read out of the key blob and must
    match the declared prefix.

    Registering a key grants no access today; nothing reads these keys yet.

    ## Errors
    - **400 Bad Request** — the submission failed a validation check; `code`
      names which.
    - **403 Forbidden** — adding a key to an account that is not your own.
    - **409 Conflict** — the account already holds this key.
    """
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keys may only be added to your own account",
        )
    key = ssh_key_service.add_key(
        session,
        user_id=user_id,
        public_key=payload.public_key,
        label=payload.label,
    )
    response.headers["Location"] = (
        f"/api/users/{user_id}/ssh-keys/{quote(key.fingerprint, safe='')}"
    )
    return key


@router.get(
    "/{fingerprint:path}",
    response_model=SshKeyRead,
    summary="Read one SSH public key",
    response_description="The key, in the same shape the collection returns.",
    responses={
        200: {"description": "The key."},
        403: {"description": "Caller may only read their own keys."},
        404: {"description": "The account holds no key with this fingerprint."},
    },
)
def get_ssh_key(
    user_id: int = Path(..., description="ID of the account that owns the key."),
    fingerprint: str = Path(..., description=FINGERPRINT_DESCRIPTION),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> SshKeyRead:
    """Read a single registered key by its fingerprint.

    ## Authorization
    You may read your own keys; administrators may read any account's.

    ## Behavior
    The same representation the collection returns, so a client never
    special-cases the path it arrived by.

    ## Errors
    - **403 Forbidden** — reading another account's key without administrator
      privileges.
    - **404 Not Found** — the account holds no key with this fingerprint.
    """
    return ssh_key_service.to_read(
        ssh_key_service.get_key(session, user_id=user_id, fingerprint=fingerprint)
    )


@router.delete(
    "/{fingerprint:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an SSH public key",
    response_description="The key is gone. Returns no body.",
    responses={
        204: {"description": "The key was removed."},
        403: {"description": "Caller may only delete their own keys."},
        404: {"description": "The account holds no key with this fingerprint."},
    },
)
def delete_ssh_key(
    user_id: int = Path(..., description="ID of the account that owns the key."),
    fingerprint: str = Path(..., description=FINGERPRINT_DESCRIPTION),
    current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> Response:
    """Remove a registered key outright.

    ## Authorization
    You may delete your own keys; administrators may delete any account's, so
    a compromised key can be revoked during an incident.

    ## Behavior
    Deletion is immediate and permanent: the row is removed, not tombstoned,
    so no later projection can mistake it for a live key.

    Deliberately **not** idempotent, unlike deleting a var. Deleting a
    fingerprint the account does not hold answers `404` rather than `204`:
    this is the operation a user reaches for after losing a laptop, and
    reporting success for a key that was never there would tell them they had
    revoked something they had not.

    Revocation currently withdraws no access, because these keys grant none
    yet.

    ## Errors
    - **403 Forbidden** — deleting another account's key without administrator
      privileges.
    - **404 Not Found** — the account holds no key with this fingerprint.
    """
    ssh_key_service.delete_key(session, user_id=user_id, fingerprint=fingerprint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
