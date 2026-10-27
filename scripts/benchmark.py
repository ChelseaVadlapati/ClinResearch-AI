"""Measure a real synthetic export in an isolated DB; no fabricated throughput."""

import argparse
import hashlib
import json
import os
import platform
import resource
import tempfile
import time
from datetime import date
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

from clinresearch.database.load import load_export
from clinresearch.database.session import initialize, make_engine
from clinresearch.ingestion.csv import REQUIRED, validate_export
from clinresearch.research.config import StudyConfig
from clinresearch.research.run import run_analysis
from clinresearch.transformations.explore import explore


def measure(source: Path, output: Path, postgres: bool = False) -> dict:
    if output.exists():
        raise FileExistsError("Benchmark output already exists")
    output.mkdir(parents=True)
    timings = {}

    def timed(name, operation):
        start = time.perf_counter()
        result = operation()
        timings[name] = time.perf_counter() - start
        return result

    export = timed("validate_seconds", lambda: validate_export(source))
    admin, schema = None, None
    with tempfile.TemporaryDirectory(prefix="clinresearch-benchmark-") as temporary:
        if postgres:
            admin = make_engine()
            if admin.dialect.name != "postgresql":
                raise ValueError("--postgres requires PostgreSQL DATABASE_URL")
            schema = "benchmark_" + uuid4().hex
            with admin.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            engine = create_engine(admin.url, connect_args={"options": f"-csearch_path={schema}"})
        else:
            engine = make_engine(f"sqlite:///{temporary}/benchmark.db")
        try:
            timed("migration_seconds", lambda: initialize(engine))
            first = timed("initial_load_seconds", lambda: load_export(engine, export))
            repeat = timed("repeat_load_seconds", lambda: load_export(engine, export))
            if any(v != {"inserted": 0, "updated": 0} for v in repeat["changes"].values()):
                raise AssertionError("Repeat import was not idempotent")
            aggregate = timed("aggregate_seconds", lambda: explore(engine, date(2025, 1, 1)))
            research = timed(
                "research_seconds",
                lambda: run_analysis(
                    engine,
                    date(2025, 1, 1),
                    date(2010, 1, 1),
                    output / "research",
                    StudyConfig(min_partition_patients=100, min_partition_class_count=20),
                ),
            )
            with engine.connect() as connection:
                db_version = connection.execute(
                    text("SELECT version()" if postgres else "SELECT sqlite_version()")
                ).scalar()
        finally:
            engine.dispose()
            if admin is not None and schema:
                with admin.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
                admin.dispose()
    cpu = "unknown"
    if Path("/proc/cpuinfo").exists():
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        )
    memory_limit = Path("/sys/fs/cgroup/memory.max")
    result = {
        "synthetic_only": True,
        "benchmark_type": "single sequential run, warm OS cache possible",
        "hardware": {
            "cpu": cpu,
            "logical_cpus": os.cpu_count(),
            "available_cpus": len(os.sched_getaffinity(0))
            if hasattr(os, "sched_getaffinity")
            else None,
            "memory_limit_bytes": memory_limit.read_text().strip()
            if memory_limit.exists()
            else None,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "peak_process_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        },
        "database": {"kind": "postgresql" if postgres else "sqlite", "version": db_version},
        "input_sha256": {
            f"{name}.csv": hashlib.sha256((source / f"{name}.csv").read_bytes()).hexdigest()
            for name in REQUIRED
        },
        "tables": export.report(),
        "timings": timings,
        "initial_changes": first["changes"],
        "repeat_changes": repeat["changes"],
        "aggregate_counts": aggregate["summary"]["counts"],
        "research_status": research["evaluation"]["status"],
        "research_audit": research["cohort_audit"],
        "limitations": (
            "Single-host measurement, no production SLA, concurrency or scaling claim. "
            "Peak RSS is whole-process high-water mark."
        ),
    }
    (output / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--postgres", action="store_true")
    args = parser.parse_args()
    result = measure(args.csv_dir, args.output, args.postgres)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
