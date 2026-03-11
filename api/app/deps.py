from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.db import get_session
from app.models import UserORM


def get_current_user(
    x_auth_request_email: str | None = Header(None),
    session: Session = Depends(get_session),
) -> UserORM:
    if not x_auth_request_email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not authenticated")

    email = x_auth_request_email.strip().lower()

    user = session.exec(
        select(UserORM).where(
            func.lower(UserORM.email) == email,
            UserORM.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    ).one_or_none()

    if user is None:
        user = UserORM(email=email)
        session.add(user)
        session.commit()
        session.refresh(user)

    return user


def require_admin(
    current_user: UserORM = Depends(get_current_user),
) -> UserORM:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return current_user


def require_self(
    user_id: int,
    current_user: UserORM = Depends(get_current_user),
) -> UserORM:
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return current_user
