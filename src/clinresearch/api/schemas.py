"""Typed public API response contracts."""

from datetime import date

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    database: str
    synthetic_only: bool = True


class AgeSummary(BaseModel):
    nonmissing: int
    missing: int
    median: float | None
    minimum: int | None
    maximum: int | None


class TableQuality(BaseModel):
    input: int
    accepted: int
    rejected: int


class Changes(BaseModel):
    inserted: int
    updated: int


class ImportSummary(BaseModel):
    run_id: str
    tables: dict[str, TableQuality]
    changes: dict[str, Changes]


class DataQuality(BaseModel):
    import_runs: int
    latest_import: ImportSummary | None
    missing_demographics: dict[str, int]


class CohortSummary(BaseModel):
    synthetic_only: bool
    as_of: date
    counts: dict[str, int]
    demographics: dict[str, dict[str, int]]
    age: AgeSummary
    data_quality: DataQuality


class MonthlyEncounters(BaseModel):
    month: str
    encounters: int


class CommonCondition(BaseModel):
    system: str
    code: str
    description: str
    occurrences: int
    patients: int
