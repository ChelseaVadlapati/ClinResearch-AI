"""Discharge-time adult cohort with explicit follow-up and one index per patient."""

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from clinresearch.database.models import Condition, Encounter, Patient

FEATURES = ["age", "length_of_stay_days", "prior_inpatient_365d", "known_condition_count"]
HORIZON = timedelta(days=30)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def build_cohort(engine: Engine, observation_end: date) -> tuple[list[dict], dict]:
    """Observation end is an exclusive UTC boundary supplied from export provenance.

    Merge overlapping/touching inpatient stays. Unknown-stop episodes cannot be
    index stays, but their starts can establish a return. A patient contributes
    their first eligible adult discharge only. Death during follow-up excludes
    the index, including positives, to keep the eligibility rule outcome-blind.
    """
    end = datetime.combine(observation_end, datetime.min.time(), UTC)
    counts = Counter()
    rows = []
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with Session(connection) as session:
            patients = session.scalars(select(Patient).order_by(Patient.id)).all()
            encounter_by_id = {}
            encounters = defaultdict(list)
            conditions = defaultdict(list)
            query = select(Encounter).order_by(Encounter.start, Encounter.id)
            for encounter in session.scalars(query):
                counts["encounters_total"] += 1
                encounter_by_id[encounter.id] = encounter
                if encounter.encounter_class.strip().lower() != "inpatient":
                    counts["excluded_non_inpatient"] += 1
                elif utc(encounter.start) >= end:
                    counts["excluded_at_or_after_observation_end"] += 1
                else:
                    if encounter.stop is not None and utc(encounter.stop) < utc(encounter.start):
                        raise ValueError(
                            "Negative inpatient duration; repair source data before analysis"
                        )
                    counts["inpatient_records"] += 1
                    encounters[encounter.patient_id].append(encounter)
            for condition in session.scalars(select(Condition)):
                conditions[condition.patient_id].append(condition)
            counts["patients_total"] = len(patients)
            for patient in patients:
                episodes = []
                for encounter in encounters[patient.id]:
                    start = utc(encounter.start)
                    stop = utc(encounter.stop) if encounter.stop else None
                    if episodes and (episodes[-1]["stop"] is None or start <= episodes[-1]["stop"]):
                        previous = episodes[-1]
                        previous["stop"] = (
                            max(previous["stop"], stop)
                            if previous["stop"] is not None and stop is not None
                            else None
                        )
                        counts["merged_encounters"] += 1
                    else:
                        episodes.append({"id": encounter.id, "start": start, "stop": stop})
                counts["episodes_total"] += len(episodes)
                if not episodes:
                    counts["patients_without_inpatient_before_end"] += 1
                selected = False
                for i, episode in enumerate(episodes):
                    if selected:
                        counts["not_selected_after_index"] += 1
                        continue
                    discharge = episode["stop"]
                    if discharge is None:
                        counts["excluded_missing_stop"] += 1
                        continue
                    age = (
                        discharge.year
                        - patient.birth_date.year
                        - (
                            (discharge.month, discharge.day)
                            < (patient.birth_date.month, patient.birth_date.day)
                        )
                    )
                    if age < 18:
                        counts["excluded_under_18"] += 1
                        continue
                    if discharge + HORIZON >= end:
                        counts["excluded_incomplete_followup"] += 1
                        continue
                    if patient.death_date and patient.death_date <= (discharge + HORIZON).date():
                        counts["excluded_death_by_horizon"] += 1
                        continue
                    # Conditions have date-only onset: same-day entries may be post-discharge.
                    known = []
                    for condition in conditions[patient.id]:
                        if condition.start >= discharge.date():
                            continue
                        linked = encounter_by_id.get(condition.encounter_id)
                        # A backdated onset does not make a future encounter available.
                        if condition.encounter_id and (
                            linked is None
                            or linked.patient_id != patient.id
                            or linked.stop is None
                            or utc(linked.start) > discharge
                            or utc(linked.stop) > discharge
                        ):
                            continue
                        known.append(condition)
                    outcome = int(
                        any(
                            discharge < other["start"] <= discharge + HORIZON
                            for other in episodes[i + 1 :]
                        )
                    )
                    rows.append(
                        {
                            "patient_id": patient.id,
                            "encounter_id": episode["id"],
                            "discharge": discharge.isoformat(),
                            "readmission_30d": outcome,
                            "age": age,
                            "length_of_stay_days": (discharge - episode["start"]).total_seconds()
                            / 86400,
                            "prior_inpatient_365d": sum(
                                discharge - timedelta(days=365) <= earlier["start"] < episode["start"]
                                for earlier in episodes[:i]
                            ),
                            "known_condition_count": len({(c.system, c.code) for c in known}),
                            "known_conditions": sorted({c.description for c in known}),
                        }
                    )
                    selected = True
                if not selected:
                    counts["patients_without_eligible_index"] += 1
                    if episodes:
                        counts["patients_with_no_eligible_episode"] += 1
    for key in (
        "encounters_total", "excluded_non_inpatient", "excluded_at_or_after_observation_end",
        "inpatient_records", "merged_encounters", "episodes_total", "excluded_missing_stop",
        "excluded_under_18", "excluded_incomplete_followup", "excluded_death_by_horizon",
        "not_selected_after_index", "patients_without_eligible_index",
        "patients_without_inpatient_before_end", "patients_with_no_eligible_episode",
    ):
        counts.setdefault(key, 0)
    counts["eligible_patients"] = len(rows)
    counts["positive_outcomes"] = sum(row["readmission_30d"] for row in rows)
    return sorted(rows, key=lambda row: (row["discharge"], row["patient_id"])), dict(counts)
