"""Parameterized cohort selection and aggregate exports; never return patient rows."""

import csv
import io
from datetime import UTC, date, datetime
from importlib.metadata import version

from sqlalchemy import Date, case, extract, literal, select
from sqlalchemy.orm import Session

from clinresearch.api.schemas import CohortSummary
from clinresearch.database.models import Encounter, ImportRun, Patient
from clinresearch.transformations.summaries import (
    cohort_summary,
    common_conditions,
    monthly_encounters,
)


def explore(
    engine,
    as_of: date,
    minimum_age=None,
    maximum_age=None,
    gender=None,
    encounter_class=None,
    encounter_start=None,
    encounter_end=None,
) -> dict:
    """Select patients; charts include their full history, not only matching visits."""
    if minimum_age is not None and maximum_age is not None and minimum_age > maximum_age:
        raise ValueError("minimum_age must not exceed maximum_age")
    if encounter_start and encounter_end and encounter_start >= encounter_end:
        raise ValueError("encounter_start must precede encounter_end")
    end = case((Patient.death_date < as_of, Patient.death_date), else_=literal(as_of, Date))
    before_birthday = (extract("month", end) * 100 + extract("day", end)) < (
        extract("month", Patient.birth_date) * 100 + extract("day", Patient.birth_date)
    )
    age = (
        extract("year", end)
        - extract("year", Patient.birth_date)
        - case((before_birthday, 1), else_=0)
    )
    selection = select(Patient.id)
    if minimum_age is not None:
        selection = selection.where(age >= minimum_age)
    if maximum_age is not None:
        selection = selection.where(age <= maximum_age, Patient.birth_date <= end)
    if gender:
        selection = selection.where(Patient.gender == gender)
    if encounter_class or encounter_start or encounter_end:
        visits = select(Encounter.patient_id)
        if encounter_class:
            visits = visits.where(Encounter.encounter_class == encounter_class)
        if encounter_start:
            visits = visits.where(
                Encounter.start >= datetime.combine(encounter_start, datetime.min.time(), UTC)
            )
        if encounter_end:
            visits = visits.where(
                Encounter.start < datetime.combine(encounter_end, datetime.min.time(), UTC)
            )
        selection = selection.where(Patient.id.in_(visits))
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            summary = CohortSummary.model_validate(
                cohort_summary(connection, as_of, selection)
            ).model_dump(mode="json")
            monthly = monthly_encounters(connection, selection)
            conditions = common_conditions(connection, 100, selection)
            with Session(connection) as session:
                latest = session.scalar(
                    select(ImportRun)
                    .order_by(ImportRun.imported_at.desc(), ImportRun.id.desc())
                    .limit(1)
                )
                source = {
                    "latest_import_at": latest.imported_at.isoformat() if latest else None,
                    "latest_dataset_version": latest.report.get("source", {}).get(
                        "dataset", "CSV version not supplied"
                    )
                    if latest
                    else None,
                    "latest_format": latest.report.get("source", {}).get("format", "Synthea CSV")
                    if latest
                    else None,
                    "software_version": version("clinresearch-ai"),
                    "scope": "Latest batch metadata; database may contain earlier imports.",
                }
    return {
        "synthetic_only": True,
        "filters": {
            "as_of": as_of.isoformat(),
            "minimum_age": minimum_age,
            "maximum_age": maximum_age,
            "gender": gender,
            "encounter_class": encounter_class,
            "encounter_start": encounter_start.isoformat() if encounter_start else None,
            "encounter_end_exclusive": encounter_end.isoformat() if encounter_end else None,
        },
        "scope": "Selected patients and full recorded history. Import audit is database-wide.",
        "summary": summary,
        "monthly": monthly,
        "conditions": conditions,
        "source": source,
    }


def aggregate_csv(report: dict) -> str:
    """Only aggregate counts; never a patient-level download or arbitrary text cell."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "measure", "count"])
    for key, count in report["summary"]["counts"].items():
        writer.writerow(["counts", key, count])
    for row in report["monthly"]:
        writer.writerow(["monthly_encounters", row["month"], row["encounters"]])
    return output.getvalue()
