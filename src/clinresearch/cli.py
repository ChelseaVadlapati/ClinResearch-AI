"""Command-line schema creation and audited CSV ingestion."""

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from clinresearch.configuration import configure_logging
from clinresearch.database.load import load_export
from clinresearch.database.session import initialize, make_engine
from clinresearch.ingestion.csv import SchemaError, validate_export


def main() -> None:
    """Import synthetic records; exit 2 after a partial load with rejected rows."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    ingest = sub.add_parser("ingest")
    ingest.add_argument("directory", type=Path)
    ingest.add_argument("--report", type=Path, required=True)
    fhir = sub.add_parser("ingest-fhir", help="Import synthetic FHIR R4 resources or Bundles")
    fhir.add_argument("directory", type=Path)
    fhir.add_argument("--dataset", required=True, help="Stable synthetic dataset version namespace")
    fhir.add_argument("--synthetic-only", action="store_true", required=True)
    fhir.add_argument("--report", type=Path, required=True)
    research = sub.add_parser("analyze", help="Simulated notes and temporal readmission evaluation")
    research.add_argument("--observation-end", type=date.fromisoformat, required=True)
    research.add_argument("--split-date", type=date.fromisoformat, required=True)
    research.add_argument("--output", type=Path, required=True)
    research.add_argument("--config", type=Path)
    args = parser.parse_args()
    configure_logging()
    try:
        engine = make_engine()
    except (ValueError, RuntimeError):
        parser.exit(
            1, "Invalid database configuration; check DATABASE_URL (no connection attempted)\n"
        )
    if args.command == "analyze":
        from clinresearch.research.config import load_config
        from clinresearch.research.run import run_analysis

        try:
            report = run_analysis(
                engine, args.observation_end, args.split_date, args.output, load_config(args.config)
            )
        except (OSError, SQLAlchemyError):
            parser.exit(1, "Analysis not written: database or output unavailable\n")
        except ValueError as exc:
            parser.exit(1, f"Analysis not written: {exc}\n")
        print(json.dumps(report, indent=2))
        return
    if args.command == "init-db":
        try:
            initialize(engine)
        except (OSError, SQLAlchemyError, RuntimeError):
            parser.exit(
                1, "Database initialization failed; check availability and schema compatibility\n"
            )
        return
    try:
        if args.command == "ingest-fhir":
            from clinresearch.ingestion.fhir import validate_fhir

            export = validate_fhir(args.directory, args.dataset)
        else:
            export = validate_export(args.directory)
    except SchemaError as exc:
        parser.exit(1, f"Schema validation failed; no records loaded: {exc}\n")
    # Persist validation evidence before any database commit; never log raw records.
    validation = {
        "status": "validated_not_committed",
        "tables": export.report(),
        "rejections": [asdict(r) for r in export.rejected],
    }
    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(validation, indent=2) + "\n")
    except OSError:
        parser.exit(1, "Report path unavailable; no records loaded\n")
    try:
        initialize(engine)
        report = load_export(engine, export)
    except (SQLAlchemyError, ValueError, RuntimeError):
        parser.exit(
            1, "Import failed; transaction not committed. Check database/schema/data integrity.\n"
        )
    report["status"] = "committed"
    report["rejections"] = [asdict(r) for r in export.rejected]
    try:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    except OSError:
        parser.exit(
            1, "Import committed; final report write failed. Inspect database import_runs audit.\n"
        )
    print(json.dumps({k: v for k, v in report.items() if k != "rejections"}, indent=2))
    if export.rejected:
        parser.exit(2, "Accepted rows loaded; inspect rejection report before proceeding.\n")


if __name__ == "__main__":
    main()
