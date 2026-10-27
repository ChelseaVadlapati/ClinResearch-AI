"""Versioned, bounded study choices; outcome semantics cannot silently change."""

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StudyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    version: Literal[1] = 1
    name: str = Field(default="adult-inpatient-return-v1", pattern=r"^[a-zA-Z0-9_.-]{1,80}$")
    minimum_age: int = Field(default=18, ge=18, le=120)
    maximum_age: int | None = Field(default=None, ge=18, le=120)
    index_start: str | None = None
    index_end_exclusive: str | None = None
    outcome_days: Literal[30] = 30
    lookback_days: Literal[365] = 365
    min_partition_patients: int = Field(default=10, ge=10)
    min_partition_class_count: int = Field(default=2, ge=2)
    seed: Literal[42] = 42

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.maximum_age is not None and self.maximum_age < self.minimum_age:
            raise ValueError("maximum_age must be >= minimum_age")
        start = date.fromisoformat(self.index_start) if self.index_start is not None else None
        end = (
            date.fromisoformat(self.index_end_exclusive)
            if self.index_end_exclusive is not None
            else None
        )
        if start and end and start >= end:
            raise ValueError("index_start must precede index_end_exclusive")
        return self

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


def load_config(path: Path | None) -> StudyConfig:
    return StudyConfig.model_validate_json(path.read_text()) if path else StudyConfig()
