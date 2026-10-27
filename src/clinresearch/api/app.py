"""Read-only FastAPI research endpoints. Initialize/load the DB through the CLI."""

import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError

from clinresearch.api.schemas import CohortSummary, CommonCondition, Health, MonthlyEncounters
from clinresearch.database.models import Base
from clinresearch.database.session import make_engine
from clinresearch.research.report import validate_report
from clinresearch.transformations.explore import aggregate_csv, explore
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

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Database or schema unavailable"})

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

    @application.get("/cohort/explore")
    def explore_cohort(
        as_of: date | None = None,
        minimum_age: int | None = Query(None, ge=0, le=120),
        maximum_age: int | None = Query(None, ge=0, le=120),
        gender: str | None = Query(None, max_length=30),
        encounter_class: str | None = Query(None, max_length=50),
        encounter_start: date | None = None,
        encounter_end: date | None = None,
        download: bool = False,
    ):
        try:
            result = explore(
                application.state.engine,
                as_of or date.today(),
                minimum_age,
                maximum_age,
                gender,
                encounter_class,
                encounter_start,
                encounter_end,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if download:
            return Response(
                aggregate_csv(result),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="cohort-aggregate.csv"'},
            )
        return result

    @application.get("/research/report")
    def research_report() -> dict:
        path = Path(os.environ.get("RESEARCH_REPORT_PATH", "reports/research/report.json"))
        try:
            # Read once: handle disappearance, permissions, invalid UTF-8, and malformed payloads.
            report = validate_report(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {"status": "not_run", "synthetic_only": True}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=503, detail="Research report unavailable or invalid"
            ) from exc
        return {"status": "available", "report": report}

    @application.get("/nlp/report")
    def nlp_report() -> dict:
        from clinresearch.nlp.report import public_report

        path = Path(os.environ.get("NLP_REPORT_PATH", "reports/nlp/report.json"))
        try:
            report = public_report(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {"status": "not_run", "synthetic_only": True}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                status_code=503, detail="NLP report unavailable or invalid"
            ) from exc
        return {"status": "available", "report": report}

    return application


app = create_app()
