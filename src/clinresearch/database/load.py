"""Transactional, idempotent loading plus append-only import audit."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, and_, func, or_, select, text
from sqlalchemy.orm import Session

from clinresearch.database.models import (
    Condition,
    Encounter,
    FHIRResource,
    ImportRun,
    MedicationRequest,
    Observation,
    Patient,
    RejectedRow,
)
from clinresearch.ingestion.csv import ValidatedExport

MODELS = {
    "patients": Patient,
    "encounters": Encounter,
    "conditions": Condition,
    "observations": Observation,
    "medication_requests": MedicationRequest,
    "fhir_resources": FHIRResource,
}


def load_export(engine: Engine, export: ValidatedExport) -> dict:
    """Upsert accepted records in dependency order and commit their audit atomically.

    PostgreSQL imports use a transaction-scoped advisory lock to serialize loaders.
    Reimports update stable keys; absent records are never deleted. Every run adds
    provenance, even when the clinical-style table contents remain unchanged.
    """
    run_id = str(uuid4())
    report = {"run_id": run_id, "tables": export.report(), "changes": {}}
    if export.metadata:
        report["source"] = export.metadata
    with Session(engine) as session, session.begin():
        if engine.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(72841309)"))
        for table, model in MODELS.items():
            if table not in export.rows:
                continue
            inserted = updated = 0
            existing = {row.id: row for row in session.scalars(select(model))}
            for values in export.rows[table]:
                current = existing.get(values["id"])
                if current is None:
                    session.add(model(**values))
                    inserted += 1
                else:
                    # Do not allow reassignment to invalidate existing dependent rows.
                    if (
                        hasattr(current, "patient_id")
                        and current.patient_id != values["patient_id"]
                    ):
                        raise ValueError("Existing event cannot be reassigned to another patient")
                    changed = False
                    for key, value in values.items():
                        old = getattr(current, key)
                        if isinstance(old, datetime) and old.tzinfo is None:
                            old = old.replace(tzinfo=UTC)
                        if old != value:
                            setattr(current, key, value)
                            changed = True
                    updated += int(changed)
            session.flush()
            report["changes"][table] = {"inserted": inserted, "updated": updated}
        # Reimported demographics must not invalidate retained events from older batches.
        for model, when in [
            (Encounter, Encounter.start),
            (Condition, Condition.start),
            (Observation, Observation.date),
            (MedicationRequest, MedicationRequest.authored_on),
        ]:
            event_day = func.date(when)
            invalid = session.scalar(
                select(model.id)
                .join(Patient, model.patient_id == Patient.id)
                .where(
                    or_(
                        event_day < Patient.birth_date,
                        and_(Patient.death_date.is_not(None), event_day > Patient.death_date),
                    )
                )
                .limit(1)
            )
            if invalid is not None:
                raise ValueError("Stored event outside patient lifetime; import rolled back")
        session.add(ImportRun(id=run_id, imported_at=datetime.now(UTC), report=report))
        session.flush()
        session.add_all(RejectedRow(run_id=run_id, **asdict(r)) for r in export.rejected)
    return report
