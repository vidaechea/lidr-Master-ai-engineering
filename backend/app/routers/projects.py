from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.dependencies import DbDep, CurrentUser
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(current_user: CurrentUser, db: DbDep):
    return await project_service.list_projects(db, current_user.id)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, current_user: CurrentUser, db: DbDep):
    return await project_service.create_project(db, current_user.id, body)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, current_user: CurrentUser, db: DbDep):
    project = await project_service.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, current_user: CurrentUser, db: DbDep
):
    project = await project_service.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await project_service.update_project(db, project, body)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: uuid.UUID, current_user: CurrentUser, db: DbDep):
    project = await project_service.get_project(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await project_service.delete_project(db, project)
