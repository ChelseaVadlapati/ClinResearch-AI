"""Boundary, leakage, assertion, artifact, and UI contracts for synthetic research."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from clinresearch.api.app import create_app
from clinresearch.database.models import Condition, Encounter, Patient
from clinresearch.research.cohort import FEATURES, build_cohort
from clinresearch.research.evaluate import evaluate
from clinresearch.research.notes import LABEL, extract_concepts, simulate_note
from clinresearch.research.run import run_analysis


def patient(session, name="p", birth=date(1980, 1, 1), death=None):
    session.add(
        Patient(
            id=name,
            birth_date=birth,
            death_date=death,
            gender="F",
            race="unknown",
            ethnicity="unknown",
        )
    )
    session.flush()


def encounter(session, name, start, stop, person="p", kind="inpatient"):
    session.add(
        Encounter(
            id=name,
            patient_id=person,
            start=start,
            stop=stop,
            encounter_class=kind,
            code="test",
            description="Synthetic test stay",
        )
    )
    session.flush()


START = datetime(2020, 1, 1, tzinfo=UTC)
END = date(2021, 1, 1)


@pytest.mark.parametrize("gap,expected", [(0, 0), (30, 1), (31, 0)])
def test_outcome_boundary_and_transfer_merge(engine, gap, expected):
    with Session(engine) as session:
        patient(session)
        discharge = START + timedelta(days=2)
        encounter(session, "index", START, discharge)
        encounter(
            session, "return", discharge + timedelta(days=gap), discharge + timedelta(days=gap + 1)
        )
        session.commit()
    rows, audit = build_cohort(engine, END)
    assert len(rows) == 1
    assert rows[0]["readmission_30d"] == expected
    if gap == 0:
        assert audit["merged_encounters"] == 1
        assert rows[0]["length_of_stay_days"] == 3


def test_future_data_not_in_features_or_notes(engine):
    with Session(engine) as session:
        patient(session)
        encounter(session, "index", START, START + timedelta(days=2))
        session.add(
            Condition(
                id="old",
                patient_id="p",
                encounter_id="index",
                system="SNOMED",
                start=date(2020, 1, 1),
                code="1",
                description="Hypertension",
            )
        )
        session.commit()
    before, _ = build_cohort(engine, END)
    with Session(engine) as session:
        encounter(session, "return", START + timedelta(days=10), START + timedelta(days=11))
        for name, day in [("same-day", 3), ("future", 10)]:
            session.add(
                Condition(
                    id=name,
                    patient_id="p",
                    system="SNOMED",
                    start=date(2020, 1, day),
                    code=name,
                    description="Diabetes",
                )
            )
        session.commit()
    after, _ = build_cohort(engine, END)
    assert before[0]["readmission_30d"] == 0
    assert after[0]["readmission_30d"] == 1
    assert [before[0][f] for f in FEATURES] == [after[0][f] for f in FEATURES]
    assert simulate_note(before[0]) == simulate_note(after[0])
    assert after[0]["known_condition_count"] == 1


@pytest.mark.parametrize(
    "reason,birth,death,stop,end",
    [
        ("excluded_under_18", date(2010, 1, 1), None, START + timedelta(days=2), END),
        ("excluded_missing_stop", date(1980, 1, 1), None, None, END),
        (
            "excluded_death_by_horizon",
            date(1980, 1, 1),
            date(2020, 1, 20),
            START + timedelta(days=2),
            END,
        ),
        (
            "excluded_incomplete_followup",
            date(1980, 1, 1),
            None,
            START + timedelta(days=2),
            date(2020, 2, 2),
        ),
    ],
)
def test_eligibility_exclusions(engine, reason, birth, death, stop, end):
    with Session(engine) as session:
        patient(session, birth=birth, death=death)
        encounter(session, "index", START, stop)
        session.commit()
    rows, audit = build_cohort(engine, end)
    assert not rows
    assert audit[reason] == 1


def test_outpatient_is_not_readmission_and_one_index(engine):
    with Session(engine) as session:
        patient(session)
        encounter(session, "index", START, START + timedelta(days=2))
        encounter(
            session,
            "outpatient",
            START + timedelta(days=5),
            START + timedelta(days=5, hours=1),
            kind="ambulatory",
        )
        encounter(session, "later", START + timedelta(days=60), START + timedelta(days=61))
        session.commit()
    rows, _ = build_cohort(engine, END)
    assert len(rows) == 1
    assert rows[0]["encounter_id"] == "index"
    assert rows[0]["readmission_30d"] == 0


def test_assertions_offsets_and_simulated_label():
    text = "No diabetes. Possible asthma. Family history of COPD. Hypertension."
    mentions = extract_concepts(text)
    assert [(m["concept"], m["assertion"]) for m in mentions] == [
        ("diabetes", "negated"),
        ("asthma", "uncertain"),
        ("copd", "family"),
        ("hypertension", "present"),
    ]
    assert all(text[m["start"] : m["end"]] == m["text"] for m in mentions)
    row = sample_rows()[0]
    row["known_conditions"] = ["Chronic kidney disease", "Diabetes", "No asthma"]
    note = simulate_note(row)
    assert note["text"].startswith(LABEL)
    assert {m["concept"] for m in note["concepts"]} == {"kidney_disease", "diabetes"}
    assert "readmission" not in note["text"]


def sample_rows():
    # Hand-authored software evaluation fixture; not an epidemiological cohort.
    rows = []
    for period, when in [("train", START), ("test", datetime(2020, 7, 1, tzinfo=UTC))]:
        for i in range(20):
            rows.append(
                {
                    "patient_id": f"{period}-{i}",
                    "encounter_id": f"{period}-e{i}",
                    "discharge": (when + timedelta(days=i)).isoformat(),
                    "readmission_30d": i % 2,
                    "age": 30 + i,
                    "length_of_stay_days": 1 + i % 3,
                    "prior_inpatient_365d": i % 4,
                    "known_condition_count": i % 5,
                    "known_conditions": [],
                }
            )
    return rows


def test_temporal_purge_training_only_scaler_and_repeatability():
    rows = sample_rows()
    purged = dict(rows[0], patient_id="purged", discharge="2020-06-15T00:00:00+00:00")
    report = evaluate([*rows, purged], date(2020, 7, 1))
    assert report["status"] == "evaluated"
    assert report["split"]["purged"]["patients"] == 1
    assert report["model"]["mean"][0] == 39.5
    assert report == evaluate([*rows, purged], date(2020, 7, 1))
    shifted = [dict(r, age=5000) if r["patient_id"].startswith("test") else r for r in rows]
    assert evaluate(shifted, date(2020, 7, 1))["model"] == report["model"]
    assert report["constant_baseline"]["roc_auc"] == 0.5
    assert sum(bin_["count"] for bin_ in report["calibration"]) == 20
    assert report["bootstrap_valid_replicates"] > 450


def test_small_or_single_class_data_never_reports_scores():
    assert evaluate([], date(2020, 7, 1))["status"] == "insufficient_data"
    rows = [dict(row, readmission_30d=0) for row in sample_rows()]
    report = evaluate(rows, date(2020, 7, 1))
    assert report["status"] == "insufficient_data"
    assert "metrics" not in report
    with pytest.raises(ValueError, match="one index"):
        evaluate([*rows, rows[0]], date(2020, 7, 1))


def test_artifacts_api_and_no_overwrite(loaded, tmp_path, monkeypatch):
    output = tmp_path / "analysis"
    report = run_analysis(loaded, date(2025, 1, 1), date(2024, 1, 1), output)
    assert report["evaluation"]["status"] == "insufficient_data"
    assert (output / "cohort.csv").exists()
    assert (output / "simulated_notes.jsonl").exists()
    monkeypatch.setenv("RESEARCH_REPORT_PATH", str(output / "report.json"))
    with TestClient(create_app(loaded)) as client:
        response = client.get("/research/report")
        assert response.status_code == 200
        assert response.json()["report"] == report
        (output / "report.json").write_text("broken")
        assert client.get("/research/report").status_code == 503
        (output / "report.json").unlink()
        assert client.get("/research/report").json()["status"] == "not_run"
    with pytest.raises(FileExistsError):
        run_analysis(loaded, date(2025, 1, 1), date(2024, 1, 1), output)
    with pytest.raises(ValueError, match="precede"):
        run_analysis(loaded, date(2024, 1, 1), date(2025, 1, 1), tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_backdated_condition_from_future_encounter_is_unavailable(engine):
    with Session(engine) as session:
        patient(session)
        encounter(session, "index", START, START + timedelta(days=2))
        session.commit()
    before, _ = build_cohort(engine, END)
    with Session(engine) as session:
        encounter(session, "future", START + timedelta(days=60), START + timedelta(days=61))
        session.add(
            Condition(
                id="backdated",
                patient_id="p",
                encounter_id="future",
                system="SNOMED",
                start=date(2019, 1, 1),
                code="future-code",
                description="Diabetes",
            )
        )
        session.commit()
    after, _ = build_cohort(engine, END)
    assert after == before
    assert simulate_note(after[0]) == simulate_note(before[0])


def test_complete_cohort_flow_reconciles_all_units(engine, tmp_path):
    with Session(engine) as session:
        patient(session)
        patient(session, name="outpatient-only")
        patient(session, name="child", birth=date(2010, 1, 1))
        encounter(session, "index", START, START + timedelta(days=2))
        encounter(session, "transfer", START + timedelta(days=1), START + timedelta(days=3))
        encounter(session, "later", START + timedelta(days=60), START + timedelta(days=61))
        encounter(session, "outside", datetime(2021, 1, 1, tzinfo=UTC), None)
        encounter(session, "outpatient", START, START, person="outpatient-only", kind="ambulatory")
        encounter(session, "minor", START, START, person="child")
        session.commit()
    report = run_analysis(engine, END, date(2020, 7, 1), tmp_path / "flow")
    audit = report["cohort_audit"]
    assert audit["encounters_total"] == 6
    assert audit["inpatient_records"] == 4
    assert audit["merged_encounters"] == 1
    assert audit["episodes_total"] == 3
    assert audit["not_selected_after_index"] == 1
    assert audit["excluded_under_18"] == 1
    assert audit["eligible_patients"] == 1
    assert audit["patients_without_eligible_index"] == 2
    totals = {
        unit: sum(row["count"] for row in report["cohort_flow"] if row["unit"] == unit)
        for unit in ("record", "episode", "patient")
    }
    assert totals == {"record": 6, "episode": 3, "patient": 3}
    assert (tmp_path / "flow" / "cohort_flow.csv").exists()


def test_single_observed_outcome_never_fits(monkeypatch):
    rows = [dict(row, readmission_30d=int(i == 0)) for i, row in enumerate(sample_rows())]

    def forbidden_fit(*args, **kwargs):
        pytest.fail("A cohort with one observed outcome must not fit a model")

    monkeypatch.setattr("clinresearch.research.evaluate.LogisticRegression.fit", forbidden_fit)
    report = evaluate(rows, date(2020, 7, 1))
    assert report["status"] == "insufficient_data"
    assert "model" not in report
    assert "metrics" not in report


def test_row_order_does_not_change_model_or_bootstrap():
    rows = sample_rows()
    assert evaluate(rows, date(2020, 7, 1)) == evaluate(list(reversed(rows)), date(2020, 7, 1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("readmission_30d", 2),
        ("readmission_30d", float("nan")),
        ("length_of_stay_days", -1),
        ("age", float("inf")),
    ],
)
def test_invalid_model_inputs_fail_closed(field, value):
    rows = sample_rows()
    rows[0][field] = value
    with pytest.raises(ValueError):
        evaluate(rows, date(2020, 7, 1))


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(notes=[]),
        lambda r: r["cohort_flow"][0].update(count=999),
        lambda r: r.update(observation_end_exclusive="invalid"),
        lambda r: r["evaluation"].update(split_date="2030-01-01"),
        lambda r: r["evaluation"].update(status="unknown"),
        lambda r: r["evaluation"].update(metrics={"roc_auc": 0.99}),
        lambda r: r["evaluation"]["split"]["train"].update(patients=-1),
        lambda r: r.update(synthetic_only=False),
        lambda r: r.update(generated_at="not-a-timestamp"),
    ],
)
def test_malformed_nested_reports_return_503(loaded, tmp_path, monkeypatch, change):
    output = tmp_path / "bad-report"
    report = run_analysis(loaded, date(2025, 1, 1), date(2024, 1, 1), output)
    change(report)
    path = output / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setenv("RESEARCH_REPORT_PATH", str(path))
    with TestClient(create_app(loaded)) as client:
        response = client.get("/research/report")
        assert response.status_code == 503
        assert response.json() == {"detail": "Research report unavailable or invalid"}


def test_evaluated_report_round_trip_and_nan_rejected(loaded, tmp_path, monkeypatch):
    output = tmp_path / "evaluation"
    report = run_analysis(loaded, date(2025, 1, 1), date(2024, 1, 1), output)
    report["evaluation"] = evaluate(sample_rows(), date(2020, 7, 1))
    report["cohort_audit"] = {"eligible_patients": 40, "positive_outcomes": 20}
    report["notes"]["count"] = 40
    report.pop("cohort_flow", None)
    path = output / "report.json"
    path.write_text(json.dumps(report))
    monkeypatch.setenv("RESEARCH_REPORT_PATH", str(path))
    with TestClient(create_app(loaded)) as client:
        assert client.get("/research/report").status_code == 200
        report["evaluation"]["metrics"]["roc_auc"] = float("nan")
        path.write_text(json.dumps(report))
        assert client.get("/research/report").status_code == 503


def test_invalid_utf8_report_returns_503(loaded, tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_bytes(bytes([255]))
    monkeypatch.setenv("RESEARCH_REPORT_PATH", str(path))
    with TestClient(create_app(loaded)) as client:
        assert client.get("/research/report").status_code == 503


def test_legacy_negative_duration_aborts_cohort(loaded):
    if loaded.dialect.name != "sqlite":
        pytest.skip("Legacy SQLite constraint bypass is specific to this regression fixture")
    with Session(loaded) as session:
        session.execute(text("PRAGMA ignore_check_constraints=ON"))
        row = session.scalar(select(Encounter))
        row.encounter_class = "inpatient"
        row.stop = row.start - timedelta(seconds=1)
        session.commit()
        session.execute(text("PRAGMA ignore_check_constraints=OFF"))
    with pytest.raises(ValueError, match="Negative inpatient duration"):
        build_cohort(loaded, date(2025, 1, 1))
