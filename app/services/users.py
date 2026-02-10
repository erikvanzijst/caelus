from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import UserRead, UserORM, UserCreate
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
    return list(session.exec(select(UserORM)).all())


def get_user(session: Session, *, user_id: int) -> UserRead:
    user = session.get(UserORM, user_id)
    if not user:
        raise NotFoundException("User not found")
    return UserRead.model_validate(user)


def delete_user(session: Session, *, user_id: int) -> None:
    user = session.get(UserORM, user_id)
    if not user:
        raise NotFoundException("User not found")
    session.delete(user)
    session.commit()
    # No need to verify deletion; operation successful.
    return None
