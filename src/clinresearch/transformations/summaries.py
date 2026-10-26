"""Descriptive summaries of loaded synthetic records; no clinical inference."""

from datetime import date

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from clinresearch.database.models import Condition, Encounter, ImportRun, Observation, Patient


def cohort_summary(engine: Engine, as_of: date) -> dict:
    """Summarize all loaded patients; as_of affects ages only, not cohort membership."""
    with engine.connect() as connection:
        patients = pd.read_sql(select(Patient), connection)
    ages = []
    for row in patients.itertuples():
        end = min(row.death_date, as_of) if row.death_date else as_of
        if row.birth_date <= end:
            ages.append(
                end.year
                - row.birth_date.year
                - ((end.month, end.day) < (row.birth_date.month, row.birth_date.day))
            )
    demographics = {
        column: {str(k): int(v) for k, v in patients[column].value_counts().sort_index().items()}
        for column in ("gender", "race", "ethnicity")
    }
    with Session(engine) as session:
        counts = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            for model in (Patient, Encounter, Condition, Observation)
        }
        latest = session.scalar(
            select(ImportRun).order_by(ImportRun.imported_at.desc(), ImportRun.id.desc()).limit(1)
        )
        runs = session.scalar(select(func.count()).select_from(ImportRun))
        quality = {
            "import_runs": runs,
            "latest_import": latest.report if latest else None,
            "missing_demographics": {
                column: int((patients[column] == "unknown").sum()) for column in demographics
            },
        }
    return {
        "synthetic_only": True,
        "as_of": as_of,
        "counts": counts,
        "demographics": demographics,
        "age": {
            "nonmissing": len(ages),
            "missing": len(patients) - len(ages),
            "median": float(pd.Series(ages).median()) if ages else None,
            "minimum": min(ages) if ages else None,
            "maximum": max(ages) if ages else None,
        },
        "data_quality": quality,
    }


def monthly_encounters(engine: Engine) -> list[dict]:
    """Count encounter starts in UTC calendar months, including zero-count gaps."""
    with engine.connect() as connection:
        frame = pd.read_sql(select(Encounter.start), connection)
    if frame.empty:
        return []
    month = pd.to_datetime(frame["start"], utc=True).dt.strftime("%Y-%m")
    counts = month.value_counts().sort_index()
    months = pd.period_range(counts.index.min(), counts.index.max(), freq="M")
    return [{"month": str(m), "encounters": int(counts.get(str(m), 0))} for m in months]


def common_conditions(engine: Engine, limit: int = 10) -> list[dict]:
    """Rank condition occurrences, also counting distinct affected patients.

    A patient may contribute multiple occurrences; neither count is prevalence.
    Description is a deterministic representative label per coding system/code.
    """
    query = (
        select(
            Condition.system,
            Condition.code,
            func.min(Condition.description).label("description"),
            func.count().label("occurrences"),
            func.count(func.distinct(Condition.patient_id)).label("patients"),
        )
        .join(Patient, Patient.id == Condition.patient_id)
        .group_by(Condition.system, Condition.code)
        .order_by(func.count().desc(), Condition.system, Condition.code)
        .limit(limit)
    )
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]
