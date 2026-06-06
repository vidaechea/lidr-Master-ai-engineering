from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=128)


class IngestionRunResponse(BaseModel):
    job_id: uuid.UUID
    source_name: str
    status: Literal["pending", "running", "completed", "failed"]


class IngestionJobView(BaseModel):
    job_id: uuid.UUID
    source_name: str
    status: Literal["pending", "running", "completed", "failed"]
    documents_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
