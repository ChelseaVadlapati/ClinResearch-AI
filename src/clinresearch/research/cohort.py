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
    with Session(engine) as session:
        patients = session.scalars(select(Patient).order_by(Patient.id)).all()
        encounters = defaultdict(list)
        conditions = defaultdict(list)
        for encounter in session.scalars(select(Encounter).order_by(Encounter.start, Encounter.id)):
            if encounter.encounter_class.lower() == "inpatient" and utc(encounter.start) < end:
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
            selected = False
            for i, episode in enumerate(episodes):
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
                known = [c for c in conditions[patient.id] if c.start < discharge.date()]
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
                break
            if not selected:
                counts["patients_without_eligible_index"] += 1
    counts["eligible_patients"] = len(rows)
    counts["positive_outcomes"] = sum(row["readmission_30d"] for row in rows)
    return sorted(rows, key=lambda row: (row["discharge"], row["patient_id"])), dict(counts)
