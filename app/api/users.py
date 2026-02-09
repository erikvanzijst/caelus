from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models import Deployment, User
from app.schemas import DeploymentCreate, DeploymentRead, UserCreate, UserRead
from app.services import deployments as deployment_service
from app.services import users as user_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> User:
    return user_service.create_user(session, email=payload.email)


@router.get("", response_model=list[UserRead])
def list_users(session: Session = Depends(get_session)) -> list[User]:
    return user_service.list_users(session)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, session: Session = Depends(get_session)) -> User:
    try:
        return user_service.get_user(session, user_id=user_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{user_id}/deployments",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment(
    user_id: int, payload: DeploymentCreate, session: Session = Depends(get_session)
) -> Deployment:
    try:
        return deployment_service.create_deployment(
            session,
            user_id=user_id,
            template_id=payload.template_id,
            domainname=payload.domainname,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{user_id}/deployments", response_model=list[DeploymentRead])
def list_deployments(user_id: int, session: Session = Depends(get_session)) -> list[Deployment]:
    return deployment_service.list_deployments(session, user_id=user_id)


@router.get("/{user_id}/deployments/{deployment_id}", response_model=DeploymentRead)
def get_deployment(
    user_id: int, deployment_id: int, session: Session = Depends(get_session)
) -> Deployment:
    try:
        return deployment_service.get_deployment(
            session, user_id=user_id, deployment_id=deployment_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
