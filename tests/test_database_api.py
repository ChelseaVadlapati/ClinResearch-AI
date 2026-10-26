"""Database constraints, joins, idempotency, aggregation, and HTTP contracts."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from clinresearch.api.app import create_app
from clinresearch.database.load import load_export
from clinresearch.database.models import Condition, Encounter, ImportRun, Patient, RejectedRow
from clinresearch.ingestion.csv import validate_export
from clinresearch.transformations.summaries import cohort_summary


def test_idempotency_and_joins(loaded, fixture_dir):
    report = load_export(loaded, validate_export(fixture_dir))
    assert all(v == {"inserted": 0, "updated": 0} for v in report["changes"].values())
    with Session(loaded) as session:
        assert session.scalar(select(func.count()).select_from(ImportRun)) == 2
        rows = session.execute(
            select(Patient.id, Encounter.id, Condition.code)
            .join(Encounter, Patient.id == Encounter.patient_id)
            .join(Condition, Condition.encounter_id == Encounter.id)
        ).all()
        assert len(rows) == 3
        assert {r[2] for r in rows} == {"38341003", "10509002"}


def test_update_and_audit(loaded, fixture_dir):
    export = validate_export(fixture_dir)
    export.rows["patients"][0]["race"] = "unknown"
    export.reject("patients", 9, {"Id": "invalid"}, "invalid UUID")
    export.input_counts["patients"] += 1
    report = load_export(loaded, export)
    assert report["changes"]["patients"] == {"inserted": 0, "updated": 1}
    with Session(loaded) as session:
        rejection = session.scalar(select(RejectedRow))
        assert rejection.run_id == report["run_id"]
        assert rejection.raw == {"Id": "invalid"}


def test_database_fk_enforced(loaded):
    with Session(loaded) as session, pytest.raises(IntegrityError):
        row = session.scalar(select(Encounter))
        row.patient_id = "ffffffff-0000-4000-8000-000000000000"
        session.commit()


def test_transaction_rolls_back(loaded, fixture_dir):
    export = validate_export(fixture_dir)
    export.rows["patients"][0]["race"] = "changed"
    export.rows["encounters"][0]["patient_id"] = export.rows["patients"][1]["id"]
    with pytest.raises(ValueError, match="reassigned"):
        load_export(loaded, export)
    with Session(loaded) as session:
        assert session.get(Patient, export.rows["patients"][0]["id"]).race == "white"
        assert session.scalar(select(func.count()).select_from(ImportRun)) == 1


def test_api_responses(loaded):
    with TestClient(create_app(loaded)) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "database": "ready",
            "synthetic_only": True,
        }
        response = client.get("/cohort/summary?as_of=2025-01-01")
        assert response.status_code == 200
        summary = response.json()
        assert summary["counts"] == dict(patients=3, encounters=3, conditions=3, observations=3)
        assert summary["age"] == dict(nonmissing=3, missing=0, median=34, minimum=24, maximum=45)
        assert summary["demographics"]["gender"] == {"F": 1, "M": 1, "unknown": 1}
        assert summary["data_quality"]["missing_demographics"]["gender"] == 1
        assert client.get("/encounters/monthly").json() == [
            {"month": "2024-01", "encounters": 2},
            {"month": "2024-02", "encounters": 0},
            {"month": "2024-03", "encounters": 1},
        ]
        condition = client.get("/conditions/common?limit=1").json()
        assert condition == [
            {
                "system": "SNOMED-CT",
                "code": "38341003",
                "description": "Hypertension",
                "occurrences": 2,
                "patients": 2,
            }
        ]
        assert client.get("/conditions/common?limit=0").status_code == 422
        assert client.get("/conditions/common?limit=101").status_code == 422
        assert client.get("/cohort/summary?as_of=not-a-date").status_code == 422


def test_empty_database(engine):
    with TestClient(create_app(engine)) as client:
        summary = client.get("/cohort/summary").json()
        assert summary["counts"]["patients"] == 0
        assert summary["age"]["median"] is None
        assert summary["data_quality"]["latest_import"] is None
        assert client.get("/encounters/monthly").json() == []
        assert client.get("/conditions/common").json() == []


def test_age_before_birth_is_missing(loaded):
    summary = cohort_summary(loaded, date(1970, 1, 1))
    assert summary["age"]["missing"] == 3
    assert summary["age"]["median"] is None


def test_health_missing_schema(engine):
    Patient.__table__.drop(engine) if engine.dialect.name == "sqlite" else None
    if engine.dialect.name == "postgresql":
        # Drop only an independent audit table; patient table has FK dependents.
        RejectedRow.__table__.drop(engine)
    with TestClient(create_app(engine)) as client:
        assert client.get("/health").status_code == 503


def test_database_rejects_cross_patient_encounter(loaded):
    with Session(loaded) as session, pytest.raises(IntegrityError):
        row = session.scalar(select(Condition).where(Condition.code == "10509002"))
        row.encounter_id = "10000000-0000-4000-8000-000000000002"
        session.commit()
