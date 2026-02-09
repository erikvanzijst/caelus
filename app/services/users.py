from __future__ import annotations

from sqlmodel import Session, select

from app.models import User
from app.services.errors import NotFoundError


def create_user(session: Session, *, email: str) -> User:
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def list_users(session: Session) -> list[User]:
    return list(session.exec(select(User)).all())


def get_user(session: Session, *, user_id: int) -> User:
    user = session.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return user
