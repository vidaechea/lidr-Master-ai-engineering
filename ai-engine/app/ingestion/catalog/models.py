from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CatalogDecision(str, Enum):
    INCLUDE = "include"
    REVIEW = "review"
    EXCLUDE = "exclude"


class CatalogQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completeness: int = Field(ge=1, le=5)
    consistency: int = Field(ge=1, le=5)
    actuality: int = Field(ge=1, le=5)
    reliability: int = Field(ge=1, le=5)


class CatalogSensitivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_pii: bool
    pii_flags: list[str] = Field(default_factory=list)
    access_level: Literal["public", "internal", "confidential", "restricted"]


class CatalogSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    location: str = Field(min_length=1, max_length=512)
    format: str = Field(min_length=1, max_length=32)
    description: str | None = None
    owners: list[str] = Field(default_factory=list)
    volume_estimate: str | None = None
    refresh_declared: str | None = None
    refresh_observed: str | None = None
    quality: CatalogQuality | None = None
    sensitivity: CatalogSensitivity | None = None
    lineage: list[str] = Field(default_factory=list)
    decision: CatalogDecision
    decision_reason: str | None = None
    last_audited: datetime | None = None


class DataCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    description: str | None = None
    sources: list[CatalogSource] = Field(default_factory=list)

    def find(self, source_name: str) -> CatalogSource | None:
        for source in self.sources:
            if source.name == source_name:
                return source
        return None

    def included_sources(self) -> list[CatalogSource]:
        return [s for s in self.sources if s.decision is CatalogDecision.INCLUDE]
