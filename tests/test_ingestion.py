"""Validation policies are checked using explicit row-level mutations."""

import csv
import shutil

import pytest

from clinresearch.ingestion.csv import SchemaError, validate_export


def mutate(fixture_dir, tmp_path, table, operation):
    """Copy fixtures and modify records without touching the versioned originals."""
    target = tmp_path / "csv"
    shutil.copytree(fixture_dir, target)
    path = target / f"{table}.csv"
    with path.open() as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    operation(rows)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_valid_export(fixture_dir):
    result = validate_export(fixture_dir)
    assert not result.rejected
    assert all(v == {"input": 3, "accepted": 3, "rejected": 0} for v in result.report().values())
    assert result.rows["patients"][2]["gender"] == "unknown"
    assert result.rows["observations"][0]["numeric_value"] == 120
    assert result.rows["observations"][2]["numeric_value"] is None
    assert result.rows["encounters"][2]["stop"] is None


@pytest.mark.parametrize("missing_file", [True, False])
def test_schema_failure(fixture_dir, tmp_path, missing_file):
    shutil.copytree(fixture_dir, tmp_path / "csv")
    path = tmp_path / "csv" / "patients.csv"
    if missing_file:
        path.unlink()
    else:
        path.write_text("Id,BIRTHDATE\n")
    with pytest.raises(SchemaError):
        validate_export(tmp_path / "csv")


@pytest.mark.parametrize(
    ("table", "field", "value", "reason"),
    [
        ("patients", "Id", "bad", "UUID"),
        ("patients", "BIRTHDATE", "01/02/2000", "ISO date"),
        ("patients", "BIRTHDATE", "2024-02-30", "ISO date"),
        ("patients", "DEATHDATE", "1970-01-01", "precedes"),
        ("encounters", "STOP", "2020-01-01T00:00:00Z", "precedes"),
        ("encounters", "START", "1970-01-01T00:00:00Z", "birth"),
        ("encounters", "PATIENT", "99999999-0000-4000-8000-000000000000", "PATIENT"),
        ("conditions", "ENCOUNTER", "10000000-0000-4000-8000-000000000002", "another patient"),
        ("observations", "VALUE", "NaN", "finite"),
        ("observations", "VALUE", "inf", "finite"),
        ("observations", "VALUE", "", "missing"),
    ],
)
def test_invalid_row_reported(fixture_dir, tmp_path, caplog, table, field, value, reason):
    target = mutate(fixture_dir, tmp_path, table, lambda rows: rows[0].update({field: value}))
    result = validate_export(target)
    rejection = next(r for r in result.rejected if r.table_name == table)
    assert reason in rejection.reason
    assert rejection.row_number == 2
    assert rejection.raw[field] == value
    assert "Rejected" in caplog.text
    for counts in result.report().values():
        assert counts["input"] == counts["accepted"] + counts["rejected"]


def test_exact_duplicates(fixture_dir, tmp_path):
    target = mutate(fixture_dir, tmp_path, "patients", lambda rows: rows.append(rows[0].copy()))
    result = validate_export(target)
    assert result.report()["patients"] == {"input": 4, "accepted": 3, "rejected": 1}
    assert result.rejected[0].reason == "duplicate normalized row"


def test_conflicts_reject_all_and_children(fixture_dir, tmp_path):
    target = mutate(
        fixture_dir, tmp_path, "patients", lambda rows: rows.append({**rows[0], "GENDER": "M"})
    )
    result = validate_export(target)
    assert result.report()["patients"]["rejected"] == 2
    assert len(result.rows["encounters"]) == 1
    assert sum(r.reason == "conflicting duplicate key" for r in result.rejected) == 2


def test_optional_encounter(fixture_dir, tmp_path):
    target = mutate(fixture_dir, tmp_path, "conditions", lambda rows: rows[0].update(ENCOUNTER=""))
    result = validate_export(target)
    assert not result.rejected
    assert result.rows["conditions"][0]["encounter_id"] is None


def test_bad_field_count(fixture_dir, tmp_path):
    shutil.copytree(fixture_dir, tmp_path / "csv")
    path = tmp_path / "csv" / "patients.csv"
    with path.open("a") as handle:
        handle.write("extra,fields\n")
    result = validate_export(tmp_path / "csv")
    assert result.rejected[0].reason == "CSV field count does not match header"


def test_distinct_same_time_measurements_preserved(fixture_dir, tmp_path):
    target = mutate(
        fixture_dir, tmp_path, "observations", lambda rows: rows.append({**rows[0], "VALUE": "125"})
    )
    result = validate_export(target)
    assert not result.rejected
    assert len(result.rows["observations"]) == 4


def test_utc_month_boundary(fixture_dir, tmp_path):
    target = mutate(
        fixture_dir,
        tmp_path,
        "encounters",
        lambda rows: rows[0].update(START="2024-02-01T00:30:00+02:00", STOP=""),
    )
    result = validate_export(target)
    assert result.rows["encounters"][0]["start"].isoformat() == "2024-01-31T22:30:00+00:00"


def test_negative_duration_uses_utc_and_rejects_dependent_rows(fixture_dir, tmp_path):
    target = mutate(
        fixture_dir,
        tmp_path,
        "encounters",
        lambda rows: rows[0].update(
            START="2024-01-01T01:00:00+00:00", STOP="2024-01-01T02:00:00+02:00"
        ),
    )
    result = validate_export(target)
    assert any(
        r.table_name == "encounters" and r.reason == "STOP precedes START" for r in result.rejected
    )
    rejected_id = "10000000-0000-4000-8000-000000000001"
    assert all(row["id"] != rejected_id for row in result.rows["encounters"])
    assert all(row["encounter_id"] != rejected_id for row in result.rows["conditions"])
    assert all(row["encounter_id"] != rejected_id for row in result.rows["observations"])


def test_events_after_death_rejected(fixture_dir, tmp_path):
    target = mutate(
        fixture_dir,
        tmp_path,
        "patients",
        lambda rows: rows[0].update(DEATHDATE="2023-12-31"),
    )
    result = validate_export(target)
    assert any(r.reason == "event follows patient death" for r in result.rejected)
