"""Read-only FastAPI research endpoints. Initialize/load the DB through the CLI."""

import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError

from clinresearch.api.schemas import CohortSummary, CommonCondition, Health, MonthlyEncounters
from clinresearch.database.models import Base
from clinresearch.database.session import make_engine
from clinresearch.transformations.summaries import (
    cohort_summary,
    common_conditions,
    monthly_encounters,
)


def create_app(engine: Engine | None = None) -> FastAPI:
    """Construct an API with an injectable database for deterministic tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = engine if engine is not None else make_engine()
        yield
        if engine is None:
            app.state.engine.dispose()

    application = FastAPI(
        title="ClinResearch AI — Synthetic EHR Analytics",
        lifespan=lifespan,
        description="Synthetic research demonstration. Not clinically validated.",
    )

    @application.get("/health", response_model=Health)
    def health() -> dict:
        try:
            with application.state.engine.connect() as connection:
                for table in Base.metadata.sorted_tables:
                    connection.execute(select(table).limit(0))
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="Database or schema unavailable") from exc
        return {"status": "ok", "database": "ready", "synthetic_only": True}

    @application.get("/cohort/summary", response_model=CohortSummary)
    def summary(as_of: date | None = None) -> dict:
        return cohort_summary(application.state.engine, as_of or date.today())

    @application.get("/encounters/monthly", response_model=list[MonthlyEncounters])
    def encounters() -> list[dict]:
        return monthly_encounters(application.state.engine)

    @application.get("/conditions/common", response_model=list[CommonCondition])
    def conditions(limit: int = Query(default=10, ge=1, le=100)) -> list[dict]:
        return common_conditions(application.state.engine, limit)

    @application.get("/research/report")
    def research_report() -> dict:
        path = Path(os.environ.get("RESEARCH_REPORT_PATH", "reports/research/report.json"))
        if not path.exists():
            return {"status": "not_run", "synthetic_only": True}
        try:
            report = json.loads(path.read_text())
            if report["schema_version"] != 1 or report["synthetic_only"] is not True:
                raise ValueError("Unsupported research report")
            # Local cohort rows and note text are deliberately not API resources.
            return {
                "status": "available",
                "report": {
                    key: report[key]
                    for key in (
                        "schema_version",
                        "synthetic_only",
                        "generated_at",
                        "cohort_sha256",
                        "observation_end_exclusive",
                        "cohort_audit",
                        "notes",
                        "evaluation",
                    )
                },
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=503, detail="Research report unavailable or invalid"
            ) from exc

    return application


app = create_app()
