"""Normalized tables and persistent import provenance."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy metadata root."""


class Patient(Base):
    """Synthetic patient demographics (direct identifiers deliberately omitted)."""

    __tablename__ = "patients"
    __table_args__ = (CheckConstraint("death_date IS NULL OR death_date >= birth_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    birth_date: Mapped[date]
    death_date: Mapped[date | None]
    gender: Mapped[str]
    race: Mapped[str]
    ethnicity: Mapped[str]


class Encounter(Base):
    """One synthetic encounter, belonging to a patient."""

    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("id", "patient_id"),
        CheckConstraint("stop IS NULL OR stop >= start"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    stop: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    encounter_class: Mapped[str]
    code: Mapped[str]
    description: Mapped[str]


class Condition(Base):
    """Condition occurrence; identity is patient/encounter/start/code."""

    __tablename__ = "conditions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"], ["encounters.id", "encounters.patient_id"]
        ),
        CheckConstraint("stop IS NULL OR stop >= start"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), index=True)
    system: Mapped[str]
    start: Mapped[date]
    stop: Mapped[date | None]
    code: Mapped[str] = mapped_column(index=True)
    description: Mapped[str]


class Observation(Base):
    """Observation values retained as text; numeric values additionally parsed."""

    __tablename__ = "observations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"], ["encounters.id", "encounters.patient_id"]
        ),
    )
    category: Mapped[str]
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36), index=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    code: Mapped[str]
    description: Mapped[str]
    value: Mapped[str]
    numeric_value: Mapped[float | None]
    units: Mapped[str | None]
    value_type: Mapped[str]


class ImportRun(Base):
    """Audit of each successful import transaction, including rejected rows."""

    __tablename__ = "import_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    report: Mapped[dict] = mapped_column(JSON)


class RejectedRow(Base):
    """One auditable rejection. Row numbers are CSV records including the header."""

    __tablename__ = "rejected_rows"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    table_name: Mapped[str]
    row_number: Mapped[int]
    reason: Mapped[str]
    raw: Mapped[dict] = mapped_column(JSON)


class MedicationRequest(Base):
    """Synthetic medication orders, not evidence of dispensing or adherence."""

    __tablename__ = "medication_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"], ["encounters.id", "encounters.patient_id"]
        ),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), index=True)
    encounter_id: Mapped[str | None] = mapped_column(String(36))
    authored_on: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    system: Mapped[str]
    code: Mapped[str]
    description: Mapped[str]
    status: Mapped[str]
    intent: Mapped[str]


class FHIRResource(Base):
    """Local-only source identifiers and hashes; never a public API response."""

    __tablename__ = "fhir_resources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset: Mapped[str]
    resource_type: Mapped[str]
    resource_id: Mapped[str]
    source_file: Mapped[str]
    sha256: Mapped[str] = mapped_column(String(64))
    identifiers: Mapped[list] = mapped_column(JSON)
    coding: Mapped[list] = mapped_column(JSON)
    normalized_table: Mapped[str]
    normalized_id: Mapped[str]
