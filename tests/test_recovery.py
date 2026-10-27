"""Configuration safety, retained-data integrity and recoverable import failures."""

import json
import logging
import os
import subprocess
import sys
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from clinresearch.configuration import JsonFormatter, database_url
from clinresearch.database.load import load_export
from clinresearch.database.models import ImportRun, Patient
from clinresearch.ingestion.csv import validate_export


@pytest.mark.parametrize(
    "url",
    [
        None,
        "password-secret-not-a-url",
        "mysql://user:secret@localhost/db",
        "postgresql+psycopg://user:secret@localhost/",
    ],
)
def test_configuration_rejects_invalid_without_echoing_secrets(url):
    with pytest.raises(ValueError) as exc:
        database_url(url)
    assert "secret" not in str(exc.value)


def test_structured_logging_is_parseable():
    record = logging.LogRecord("test", logging.INFO, "test", 1, "import_completed", (), None)
    value = json.loads(JsonFormatter().format(record))
    assert value["event"] == "import_completed"
    assert value["level"] == "INFO"
    assert value["timestamp"].endswith("+00:00")


def test_demographic_update_cannot_invalidate_retained_events(loaded, fixture_dir):
    export = validate_export(fixture_dir)
    for table in export.rows:
        if table != "patients":
            export.rows[table] = []
            export.input_counts[table] = 0
    export.rows["patients"][0]["birth_date"] = date(2025, 1, 1)
    with pytest.raises(ValueError, match="lifetime"):
        load_export(loaded, export)
    with Session(loaded) as session:
        assert session.get(Patient, export.rows["patients"][0]["id"]).birth_date == date(1980, 1, 1)
        assert session.scalar(select(func.count()).select_from(ImportRun)) == 1
    recovered = load_export(loaded, validate_export(fixture_dir))
    assert all(v == {"inserted": 0, "updated": 0} for v in recovered["changes"].values())


def test_cli_bad_configuration_no_traceback_or_secret(tmp_path):
    env = {**os.environ, "DATABASE_URL": "mysql://user:private-password@localhost/db"}
    result = subprocess.run(
        [sys.executable, "-m", "clinresearch.cli", "init-db"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert "Invalid database configuration" in result.stderr
    assert "private-password" not in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_unwritable_report_does_not_load(fixture_dir, tmp_path):
    # A directory at the target path is deterministically unwritable as a report file.
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'demo.db'}"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "clinresearch.cli",
            "ingest",
            str(fixture_dir),
            "--report",
            str(tmp_path),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    assert "no records loaded" in result.stderr
    assert not (tmp_path / "demo.db").exists()


def test_final_report_failure_preserves_committed_audit(fixture_dir, tmp_path, monkeypatch, capsys):
    from pathlib import Path

    from clinresearch.cli import main
    from clinresearch.database.session import make_engine

    monkeypatch.setattr("clinresearch.cli.configure_logging", lambda: None)
    report = tmp_path / "report.json"
    url = f"sqlite:///{tmp_path / 'committed.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        sys, "argv", ["clinresearch", "ingest", str(fixture_dir), "--report", str(report)]
    )
    original = Path.write_text
    writes = 0

    def failed_final_write(path, *args, **kwargs):
        nonlocal writes
        if path == report:
            writes += 1
            if writes == 2:
                raise PermissionError("private filesystem details")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failed_final_write)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    error = capsys.readouterr().err
    assert "Import committed; final report write failed" in error
    assert "private filesystem" not in error
    engine = make_engine(url)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Patient)) == 3
        assert session.scalar(select(func.count()).select_from(ImportRun)) == 1
    engine.dispose()
