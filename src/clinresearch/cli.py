"""Command-line schema creation and audited CSV ingestion."""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    engine = make_engine()
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
        initialize(engine)
        return
    try:
        if args.command == "ingest-fhir":
            from clinresearch.ingestion.fhir import validate_fhir

            export = validate_fhir(args.directory, args.dataset)
        else:
            export = validate_export(args.directory)
    except SchemaError as exc:
        parser.exit(1, f"Schema validation failed; no records loaded: {exc}\n")
    # Check report path before committing anything to the database.
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("w") as output:
        json.dump(
            {
                "status": "validated",
                "tables": export.report(),
                "rejections": [asdict(r) for r in export.rejected],
            },
            output,
            indent=2,
        )
    initialize(engine)
    report = load_export(engine, export)
    report["rejections"] = [asdict(r) for r in export.rejected]
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "rejections"}, indent=2))
    if export.rejected:
        parser.exit(2, "Accepted rows loaded; inspect rejection report before proceeding.\n")


if __name__ == "__main__":
    main()
