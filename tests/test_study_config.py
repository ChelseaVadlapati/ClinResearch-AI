"""Configured cohort boundaries and supported descriptive uncertainty."""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session
from test_research import END, START, encounter, patient, sample_rows

from clinresearch.research.cohort import build_cohort
from clinresearch.research.config import StudyConfig, load_config
from clinresearch.research.descriptive import describe
from clinresearch.research.evaluate import evaluate
from clinresearch.research.report import validate_report
from clinresearch.research.run import run_analysis


@pytest.mark.parametrize(
    "values",
    [
        {"minimum_age": 17},
        {"minimum_age": 60, "maximum_age": 50},
        {"index_start": "bad"},
        {"index_start": "2024-01-01", "index_end_exclusive": "2023-01-01"},
        {"outcome_days": 90},
        {"min_partition_class_count": 1},
        {"unknown": 1},
    ],
)
def test_invalid_config_rejected(values):
    with pytest.raises(ValueError):
        StudyConfig(**values)


def test_cohort_config_boundaries_and_default_equivalence(engine, tmp_path):
    with Session(engine) as session:
        patient(session)
        encounter(session, "first", START, START + timedelta(days=2))
        encounter(session, "second", START + timedelta(days=60), START + timedelta(days=62))
        session.commit()
    assert build_cohort(engine, END) == build_cohort(engine, END, StudyConfig())
    rows, audit = build_cohort(engine, END, StudyConfig(index_start="2020-02-01"))
    assert rows[0]["encounter_id"] == "second"
    assert audit["excluded_index_window"] == 1
    assert rows[0]["prior_inpatient_365d"] == 1  # window filters indices, not history
    rows, audit = build_cohort(engine, END, StudyConfig(minimum_age=50))
    assert rows == []
    assert audit["excluded_config_age"] == 2
    report = run_analysis(
        engine, END, date(2020, 7, 1), tmp_path / "config", StudyConfig(index_start="2020-02-01")
    )
    assert report["study_config"]["index_start"] == "2020-02-01"
    assert report["descriptive"]["patients"] == 1
    assert report["descriptive"]["outcome_wilson_95"] is None
    report["study_config"]["minimum_age"] = 55
    with pytest.raises(ValueError, match="fingerprint"):
        validate_report(report)


def test_config_can_tighten_but_not_relax_sufficiency():
    rows = sample_rows()
    assert evaluate(rows, date(2020, 7, 1))["status"] == "evaluated"
    report = evaluate(rows, date(2020, 7, 1), StudyConfig(min_partition_patients=100))
    assert report["status"] == "insufficient_data"
    assert "metrics" not in report


def test_descriptive_interval_and_missingness():
    rows = sample_rows()
    result = describe(rows)
    assert result["positives"] == result["negatives"] == 20
    assert result["outcome_wilson_95"] == pytest.approx([0.35199527, 0.64800473])
    assert result["features"]["age"]["median"] == 39.5
    assert sum(b["count"] for b in result["features"]["age"]["histogram"]) == 40
    assert describe([])["outcome_fraction"] is None
    assert describe(rows[:1])["outcome_wilson_95"] is None
    rows[0]["age"] = None
    assert describe(rows)["features"]["age"]["missing"] == 1


def test_committed_config_has_stricter_guardrails():
    from pathlib import Path

    config = load_config(Path("configs/adult-return-v1.json"))
    assert config.min_partition_patients == 100
    assert config.min_partition_class_count == 20
