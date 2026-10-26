"""Reproducible local artifacts with aggregate-only API report support."""

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine

from clinresearch.research.cohort import FEATURES, build_cohort
from clinresearch.research.evaluate import evaluate
from clinresearch.research.notes import simulate_note
from clinresearch.research.report import validate_report


def run_analysis(engine: Engine, observation_end: date, split_date: date, output: Path) -> dict:
    """Write a new artifact directory, refusing to overwrite previous research runs."""
    if split_date >= observation_end:
        raise ValueError("split-date must precede observation-end")
    if output.exists():
        raise FileExistsError(f"Output directory already exists: {output}")
    rows, audit = build_cohort(engine, observation_end)
    evaluation = evaluate(rows, split_date)
    notes = [simulate_note(row) for row in rows]
    concepts = Counter(
        mention["concept"]
        for note in notes
        for mention in note["concepts"]
        if mention["assertion"] == "present"
    )
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    report = {
        "schema_version": 1,
        "protocol_version": "1.1",
        "cohort_flow": cohort_flow(audit),
        "synthetic_only": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "cohort_sha256": fingerprint,
        "observation_end_exclusive": observation_end.isoformat(),
        "cohort_audit": audit,
        "notes": {
            "count": len(notes),
            "template_version": "1",
            "present_concept_mentions": dict(sorted(concepts.items())),
        },
        "evaluation": evaluation,
    }
    report = validate_report(report)
    output.mkdir(parents=True, exist_ok=False)
    pd.DataFrame(report["cohort_flow"]).to_csv(output / "cohort_flow.csv", index=False)
    pd.DataFrame(
        rows,
        columns=[
            "patient_id",
            "encounter_id",
            "discharge",
            "readmission_30d",
            *FEATURES,
            "known_conditions",
        ],
    ).to_csv(output / "cohort.csv", index=False)
    (output / "simulated_notes.jsonl").write_text(
        "".join(json.dumps(note, ensure_ascii=False) + "\n" for note in notes), encoding="utf-8"
    )
    pending = output / "report.pending"
    pending.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pending.replace(output / "report.json")
    return report


def cohort_flow(audit: dict) -> list[dict]:
    """Mutually exclusive dispositions within each unit; never sum across units."""
    groups = {
        "record": [
            "excluded_non_inpatient", "excluded_at_or_after_observation_end", "inpatient_records",
        ],
        "episode": [
            "excluded_missing_stop", "excluded_under_18", "excluded_incomplete_followup",
            "excluded_death_by_horizon", "not_selected_after_index", "eligible_patients",
        ],
        "patient": [
            "patients_without_inpatient_before_end", "patients_with_no_eligible_episode",
            "eligible_patients",
        ],
    }
    totals = {"record": "encounters_total", "episode": "episodes_total", "patient": "patients_total"}
    for unit, keys in groups.items():
        if sum(audit[key] for key in keys) != audit[totals[unit]]:
            raise ValueError(f"Cohort flow does not reconcile: {unit}")
    if audit["inpatient_records"] != audit["episodes_total"] + audit["merged_encounters"]:
        raise ValueError("Merged inpatient record count does not reconcile")
    return [
        {"unit": unit, "disposition": key, "count": audit[key]}
        for unit, keys in groups.items() for key in keys
    ]
