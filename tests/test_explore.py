"""Filtered aggregates, public report contracts and row-level privacy boundaries."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clinresearch.api.app import create_app
from clinresearch.database.load import load_export
from clinresearch.ingestion.fhir import validate_fhir


def test_filters_scope_all_aggregates_and_history(loaded):
    with TestClient(create_app(loaded)) as client:
        result = client.get("/cohort/explore?as_of=2025-01-01&gender=F").json()
        assert result["summary"]["counts"] == {
            "patients": 1,
            "encounters": 2,
            "conditions": 2,
            "observations": 2,
        }
        assert result["summary"]["age"]["median"] == 45
        assert [r["encounters"] for r in result["monthly"]] == [1, 0, 1]
        assert sum(r["occurrences"] for r in result["conditions"]) == 2
        assert result["source"]["latest_import_at"]
        age = client.get("/cohort/explore?as_of=2025-01-01&minimum_age=45&maximum_age=45").json()
        assert age["summary"]["counts"]["patients"] == 1
        # Date predicates select patients; their entire history remains in the summaries.
        window = client.get(
            "/cohort/explore?encounter_start=2024-03-01&encounter_end=2024-04-01"
        ).json()
        assert window["summary"]["counts"]["encounters"] == 2
        empty = client.get("/cohort/explore?encounter_class=inpatient").json()
        assert empty["summary"]["counts"]["patients"] == 0
        assert empty["summary"]["age"]["median"] is None
        assert empty["monthly"] == []
        inject = client.get("/cohort/explore", params={"gender": "F' OR 1=1"}).json()
        assert inject["summary"]["counts"]["patients"] == 0


@pytest.mark.parametrize(
    "query",
    [
        "minimum_age=-1",
        "minimum_age=70&maximum_age=20",
        "encounter_start=2025-01-01&encounter_end=2024-01-01",
    ],
)
def test_invalid_filter_contracts(loaded, query):
    with TestClient(create_app(loaded)) as client:
        assert client.get("/cohort/explore?" + query).status_code == 422


def test_download_contains_aggregates_only(loaded):
    with TestClient(create_app(loaded)) as client:
        response = client.get("/cohort/explore?gender=F&download=true")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "counts,patients,1" in response.text
        assert "patient_id" not in response.text
        assert "00000000-0000" not in response.text


def test_fhir_source_filenames_and_identifiers_never_exposed(engine):
    export = validate_fhir(Path("tests/fixtures/fhir/bundle.json"), "synthetic-v1")
    export.metadata["files_sha256"] = {"sensitive-source-name.json": "f" * 64}
    load_export(engine, export)
    with TestClient(create_app(engine)) as client:
        response = client.get("/cohort/explore")
        assert response.status_code == 200
        assert "sensitive-source-name" not in response.text
        assert "files_sha256" not in response.text
        assert "normalized_id" not in response.text
        assert response.json()["source"]["latest_dataset_version"] == "synthetic-v1"


def test_nlp_aggregate_report_and_malformed_counts(loaded, tmp_path, monkeypatch):
    report = json.loads(Path("benchmarks/nlp/verified-results-v1.json").read_text())
    path = tmp_path / "nlp.json"
    path.write_text(json.dumps(report))
    monkeypatch.setenv("NLP_REPORT_PATH", str(path))
    with TestClient(create_app(loaded)) as client:
        response = client.get("/nlp/report")
        assert response.status_code == 200
        public = response.json()["report"]
        assert public["test_examples"] == 24
        assert "errors" not in public and "model" not in public
        assert "text" not in json.dumps(public)
        report["results"]["rules"]["confusion_matrix"][0][0] += 1
        path.write_text(json.dumps(report))
        assert client.get("/nlp/report").status_code == 503
        path.unlink()
        assert client.get("/nlp/report").json()["status"] == "not_run"
