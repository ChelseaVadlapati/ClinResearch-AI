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


def run_analysis(engine: Engine, observation_end: date, split_date: date, output: Path) -> dict:
    """Write a new artifact directory, refusing to overwrite previous research runs."""
    if split_date >= observation_end:
        raise ValueError("split-date must precede observation-end")
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
    output.mkdir(parents=True, exist_ok=False)
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
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report
