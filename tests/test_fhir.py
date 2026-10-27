"""FHIR integrity, normalized equivalence, migration and public boundary regressions."""

import copy
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from clinresearch.api.app import create_app
from clinresearch.database.load import load_export
from clinresearch.database.models import FHIRResource, MedicationRequest, Patient
from clinresearch.database.session import initialize
from clinresearch.ingestion.csv import SchemaError, validate_export
from clinresearch.ingestion.fhir import validate_fhir
from clinresearch.transformations.summaries import cohort_summary, monthly_encounters

FIXTURE = Path(__file__).parent / "fixtures/fhir/bundle.json"


def changed(tmp_path, change):
    data = json.loads(FIXTURE.read_text())
    change(data["entry"])
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(data))
    return path


def test_fhir_load_repeat_provenance_and_api(engine):
    export = validate_fhir(FIXTURE, "fictional-v1")
    assert not export.rejected
    first = load_export(engine, export)
    repeat = load_export(engine, validate_fhir(FIXTURE, "fictional-v1"))
    assert all(v == {"inserted": 0, "updated": 0} for v in repeat["changes"].values())
    assert first["source"]["resources_total"] == 13
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(FHIRResource)) == 13
        assert session.scalar(select(func.count()).select_from(MedicationRequest)) == 1
    with TestClient(create_app(engine)) as client:
        assert client.get("/health").status_code == 200
        summary = client.get("/cohort/summary?as_of=2025-01-01").json()
        assert summary["counts"] == dict(patients=3, encounters=3, conditions=3, observations=3)
        # Source hashes/identifiers remain local; the API exposes aggregates only.
        assert "source_file" not in json.dumps(summary)
        assert "normalized_id" not in json.dumps(summary)
        assert client.get("/patients").status_code == 404


def test_csv_fhir_comparable_semantics(engine, fixture_dir):
    load_export(engine, validate_export(fixture_dir))
    csv_summary = cohort_summary(engine, date(2025, 1, 1))
    csv_months = monthly_encounters(engine)
    # Compare validation outputs without combining formats in one database.
    fhir = validate_fhir(FIXTURE, "fictional-v1")
    csv = validate_export(fixture_dir)
    for table, fields in {
        "patients": ["birth_date", "death_date", "gender"],
        "encounters": ["start", "stop", "code"],
        "conditions": ["start", "stop", "code"],
        "observations": ["date", "code", "value", "numeric_value", "units"],
    }.items():

        def canonical(rows, fields=fields):
            return sorted([tuple(str(row[f]) for f in fields) for row in rows])

        # Numeric lexical forms differ (120 versus 120.0); compare numeric semantics separately.
        if table == "observations":
            fields.remove("value")
        assert canonical(csv.rows[table]) == canonical(fhir.rows[table])
    assert csv_summary["counts"]["patients"] == 3
    assert sum(row["encounters"] for row in csv_months) == 3


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda e: e[3]["resource"]["period"].update(end="2023-01-01T00:00:00Z"), "STOP precedes"),
        (
            lambda e: e[3]["resource"]["subject"].update(reference="Patient/missing"),
            "missing or ambiguous",
        ),
        (
            lambda e: e[6]["resource"]["subject"].update(
                reference="Patient/00000000-0000-4000-8000-000000000002"
            ),
            "another patient",
        ),
        (lambda e: e[9]["resource"]["valueQuantity"].update(value="NaN"), "finite numeric"),
        (lambda e: e[9]["resource"].update(effectiveDateTime="2024-01-01T00:00:00"), "timezone"),
        (lambda e: e[9]["resource"].update(code={"coding": [{"code": "x"}]}), "coding system"),
        (lambda e: e[0]["resource"].update(birthDate="2025-01-01"), "outside patient lifetime"),
    ],
)
def test_invalid_resources_and_dependents_are_audited(tmp_path, change, reason):
    result = validate_fhir(changed(tmp_path, change), "fictional-v1")
    assert any(reason in r.reason for r in result.rejected)
    for counts in result.report().values():
        assert counts["input"] == counts["accepted"] + counts["rejected"]


def test_duplicate_conflict_order_independent(tmp_path):
    def conflict(entries):
        other = copy.deepcopy(entries[0])
        other["resource"]["birthDate"] = "1970-01-01"
        entries.append(other)

    path = changed(tmp_path, conflict)
    before = validate_fhir(path, "fictional-v1")
    data = json.loads(path.read_text())
    data["entry"].reverse()
    path.write_text(json.dumps(data))
    after = validate_fhir(path, "fictional-v1")
    assert before.rows == after.rows
    assert before.report() == after.report()
    assert len(before.rows["patients"]) == 2
    assert before.report()["patients"]["rejected"] == 2


def test_exact_duplicate_and_unsupported_accounting(tmp_path):
    path = changed(
        tmp_path,
        lambda e: e.extend(
            [copy.deepcopy(e[0]), {"resource": {"resourceType": "Organization", "id": "org"}}]
        ),
    )
    result = validate_fhir(path, "fictional-v1")
    assert result.report()["patients"] == {"input": 4, "accepted": 3, "rejected": 1}
    assert result.metadata["unsupported_resource_counts"] == {"Organization": 1}


def test_fullurl_collision_rejects_both(tmp_path):
    path = changed(tmp_path, lambda e: e[1].update(fullUrl=e[0]["fullUrl"]))
    result = validate_fhir(path, "fictional-v1")
    assert len(result.rows["patients"]) == 1


def test_malformed_document_aborts(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"resourceType":"Bundle", "entry": [1], "type":"collection"}')
    with pytest.raises(SchemaError):
        validate_fhir(path, "fictional-v1")


def test_resource_files_and_namespace(tmp_path):
    data = json.loads(FIXTURE.read_text())
    for i, entry in enumerate(data["entry"]):
        resource = entry["resource"]
        if resource["resourceType"] == "Condition":
            resource["subject"]["reference"] = resource["subject"]["reference"].replace(
                "urn:uuid:", "Patient/"
            )
        (tmp_path / f"{i}.json").write_text(json.dumps(resource))
    first = validate_fhir(tmp_path, "version1")
    second = validate_fhir(tmp_path, "version2")
    assert not first.rejected
    assert {r["id"] for r in first.rows["patients"]}.isdisjoint(
        r["id"] for r in second.rows["patients"]
    )


def test_migrations_preserve_existing_records(loaded):
    with loaded.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    initialize(loaded)
    initialize(loaded)
    with Session(loaded) as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 3
        assert (
            session.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0002_fhir"
        )


def test_fhir_dashboard_with_live_api(engine, monkeypatch, tmp_path):
    from test_dashboard import test_dashboard_with_live_api as render_dashboard

    load_export(engine, validate_fhir(FIXTURE, "fictional-v1"))
    render_dashboard(engine, monkeypatch, tmp_path, "not_run")
