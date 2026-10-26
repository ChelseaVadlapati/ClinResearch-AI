"""Transactional, idempotent loading plus append-only import audit."""

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from clinresearch.database.models import (
    Condition,
    Encounter,
    ImportRun,
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
}


def load_export(engine: Engine, export: ValidatedExport) -> dict:
    """Upsert accepted records in dependency order and commit their audit atomically.

    PostgreSQL imports use a transaction-scoped advisory lock to serialize loaders.
    Reimports update stable keys; absent records are never deleted. Every run adds
    provenance, even when the clinical-style table contents remain unchanged.
    """
    run_id = str(uuid4())
    report = {"run_id": run_id, "tables": export.report(), "changes": {}}
    with Session(engine) as session, session.begin():
        if engine.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(72841309)"))
        for table, model in MODELS.items():
            inserted = updated = 0
            existing = {row.id: row for row in session.scalars(select(model))}
            for values in export.rows[table]:
                current = existing.get(values["id"])
                if current is None:
                    session.add(model(**values))
                    inserted += 1
                else:
                    # Do not allow reassignment to invalidate existing dependent rows.
                    if table == "encounters" and current.patient_id != values["patient_id"]:
                        raise ValueError(
                            "Existing encounter cannot be reassigned to another patient"
                        )
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
        session.add(ImportRun(id=run_id, imported_at=datetime.now(UTC), report=report))
        session.flush()
        session.add_all(RejectedRow(run_id=run_id, **asdict(r)) for r in export.rejected)
    return report
