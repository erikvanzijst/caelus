from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config import get_settings
from app.models import TosAcceptanceRead, UserRead, UserORM, UserCreate
from app.services.errors import NotFoundException, IntegrityException


def create_user(session: Session, payload: UserCreate) -> UserRead:
    user = UserORM.model_validate(payload)
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
        return UserRead.model_validate(user)
    except IntegrityError as exc:
        raise IntegrityException(f"Email already in use: {user.email}") from exc


def list_users(session: Session) -> list[UserRead]:
    return list(session.exec(select(UserORM).where(UserORM.deleted_at == None)).all())


def get_user(session: Session, *, user_id: int) -> UserRead:
    user = session.exec(select(UserORM).where(UserORM.id == user_id, UserORM.deleted_at == None)).one_or_none()
    if not user:
        raise NotFoundException("User not found")
    return UserRead.model_validate(user)


def get_tos_acceptance(user: UserORM) -> TosAcceptanceRead:
    """Return the user's ToS acceptance status. Always readable; `version` is
    null when the user has not yet accepted.

    `current_version` reports the version the platform currently requires, read
    from settings the same way :func:`record_tos_acceptance` validates against
    it. It is always set and is unrelated to what the user accepted: a user who
    accepted an older version sees the two differ.
    """
    return TosAcceptanceRead(
        version=user.tos_accepted_version,
        accepted_at=user.tos_accepted_at,
        current_version=get_settings().current_tos_version,
    )


def record_tos_acceptance(session: Session, *, user: UserORM, version: str) -> TosAcceptanceRead:
    """Record the current user's acceptance of the Terms of Service.

    The submitted version MUST equal the current ToS version; a mismatch is a
    409 (the terms changed under the user). Recording is idempotent for the
    current version — re-accepting simply re-stamps the acceptance time.
    """
    if version != get_settings().current_tos_version:
        raise IntegrityException(
            "Terms of Service have changed; please re-review and accept the current version"
        )
    user.tos_accepted_version = version
    user.tos_accepted_at = datetime.now(UTC)
    session.add(user)
    session.commit()
    session.refresh(user)
    return get_tos_acceptance(user)


def delete_user(session: Session, *, user_id: int) -> UserRead:
    user = session.exec(select(UserORM).where(UserORM.id == user_id, UserORM.deleted_at == None)).one_or_none()
    if not user:
        raise NotFoundException("User not found")
    user.deleted_at = user.created_at
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserRead.model_validate(user)
