from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.models import UserRead, UserCreate, DeploymentRead, DeploymentCreate
from app.services import deployments as deployment_service, users as user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: Session = Depends(get_session)) -> UserRead:
    return user_service.create_user(session, payload)


@router.get("", response_model=list[UserRead])
def list_users(session: Session = Depends(get_session)) -> list[UserRead]:
    return user_service.list_users(session)


@router.delete("/{user_id}", status_code=204)
def delete_user_endpoint(user_id: int, session: Session = Depends(get_session)) -> None:
    user_service.delete_user(session, user_id=user_id)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, session: Session = Depends(get_session)) -> UserRead:
    return user_service.get_user(session, user_id=user_id)


@router.post(
    "/{user_id}/deployments",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_deployment(
    user_id: int, payload: DeploymentCreate, session: Session = Depends(get_session)
) -> DeploymentRead:
    return deployment_service.create_deployment(session, user_id=user_id, payload=payload)


@router.get("/{user_id}/deployments", response_model=list[DeploymentRead])
def list_deployments(user_id: int, session: Session = Depends(get_session)):
    return deployment_service.list_deployments(session, user_id=user_id)


@router.get("/{user_id}/deployments/{deployment_id}", response_model=DeploymentRead)
def get_deployment(
    user_id: int, deployment_id: int, session: Session = Depends(get_session)
) -> DeploymentRead:
    return deployment_service.get_deployment(session, user_id=user_id, deployment_id=deployment_id)


@router.delete("/{user_id}/deployments/{deployment_id}", status_code=204)
def delete_deployment_endpoint(
    user_id: int, deployment_id: int, session: Session = Depends(get_session)
) -> None:
    deployment_service.delete_deployment(session, user_id=user_id, deployment_id=deployment_id)
