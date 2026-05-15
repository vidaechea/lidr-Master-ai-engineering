from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ProjectType = Literal["mobile_app", "web_saas", "internal_tool", "data_pipeline"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_type: ProjectType | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    project_type: ProjectType | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    project_type: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
