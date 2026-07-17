from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user_id
from app.db import get_db
from app.models.v1 import V1Project
from app.schemas.v1 import ProjectCreate, ProjectResponse, ProjectUpdate


router = APIRouter(prefix="/v1/projects", tags=["v1-projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    project = V1Project(user_id=UUID(user_id), **payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(V1Project).where(V1Project.user_id == UUID(user_id)).order_by(V1Project.updated_at.desc())
        )
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, user_id: str = Depends(get_current_user_id), db: Session = Depends(get_db)):
    project = db.scalar(select(V1Project).where(V1Project.id == project_id, V1Project.user_id == UUID(user_id)))
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": "Project not found"})
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    project = db.scalar(select(V1Project).where(V1Project.id == project_id, V1Project.user_id == UUID(user_id)))
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": "Project not found"})
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project
