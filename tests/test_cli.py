"""CLI persistence and exit codes are part of the import contract."""

import json
import os
import shutil
import subprocess
import sys


def test_cli_rejections_and_schema_failure(fixture_dir, tmp_path):
    source = tmp_path / "csv"
    shutil.copytree(fixture_dir, source)
    with (source / "patients.csv").open("a") as handle:
        handle.write("invalid,1980-01-01,,F,white,nonhispanic\n")
    report = tmp_path / "report.json"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'demo.db'}"}
    command = [
        sys.executable,
        "-m",
        "clinresearch.cli",
        "ingest",
        str(source),
        "--report",
        str(report),
    ]
    run = subprocess.run(command, env=env, capture_output=True, text=True)
    assert run.returncode == 2, run.stderr
    audit = json.loads(report.read_text())
    assert audit["tables"]["patients"] == {"input": 4, "accepted": 3, "rejected": 1}
    assert audit["rejections"][0]["raw"]["Id"] == "invalid"
    (source / "patients.csv").unlink()
    run = subprocess.run(command, env=env, capture_output=True, text=True)
    assert run.returncode == 1
    assert "no records loaded" in run.stderr


def test_cli_analysis(fixture_dir, tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'research.db'}"}
    ingest = subprocess.run(
        [
            sys.executable,
            "-m",
            "clinresearch.cli",
            "ingest",
            str(fixture_dir),
            "--report",
            str(tmp_path / "ingest.json"),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert ingest.returncode == 0, ingest.stderr
    command = [
        sys.executable,
        "-m",
        "clinresearch.cli",
        "analyze",
        "--observation-end",
        "2025-01-01",
        "--split-date",
        "2024-01-01",
        "--output",
        str(tmp_path / "research"),
    ]
    analysis = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert analysis.returncode == 0, analysis.stderr
    assert json.loads(analysis.stdout)["evaluation"]["status"] == "insufficient_data"
    again = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    assert again.returncode == 1
    assert "Analysis not written" in again.stderr
