"""Boundary, leakage, assertion, artifact, and UI contracts for synthetic research."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
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
