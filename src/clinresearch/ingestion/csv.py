"""Strict, deterministic validation of a complete four-file Synthea export."""

import csv
import hashlib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)
REQUIRED = {
    "patients": {"Id", "BIRTHDATE", "DEATHDATE", "GENDER", "RACE", "ETHNICITY"},
    "encounters": {"Id", "START", "STOP", "PATIENT", "ENCOUNTERCLASS", "CODE", "DESCRIPTION"},
    "conditions": {"START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION"},
    "observations": {
        "DATE",
        "PATIENT",
        "ENCOUNTER",
        "CODE",
        "DESCRIPTION",
        "VALUE",
        "UNITS",
        "TYPE",
    },
}


class SchemaError(ValueError):
    """A missing file, malformed CSV, or header prevents the entire import."""


@dataclass
class Rejection:
    """A rejected input record, with its source fields preserved."""

    table_name: str
    row_number: int
    reason: str
    raw: dict


@dataclass
class ValidatedExport:
    """Accepted records and a full accounting of every input row."""

    rows: dict[str, list[dict]] = field(default_factory=dict)
    input_counts: dict[str, int] = field(default_factory=dict)
    rejected: list[Rejection] = field(default_factory=list)

    def reject(self, table: str, number: int, raw: dict, reason: str) -> None:
        """Record and log a rejection without logging the original field values."""
        self.rejected.append(Rejection(table, number, reason, raw))
        logger.warning("Rejected %s CSV record %d: %s", table, number, reason)

    def report(self) -> dict:
        """Summarize accepted/rejected rows; accepted includes idempotent updates."""
        return {
            table: {
                "input": self.input_counts[table],
                "accepted": len(self.rows[table]),
                "rejected": sum(r.table_name == table for r in self.rejected),
            }
            for table in REQUIRED
        }


def _required(raw: dict, key: str) -> str:
    value = raw.get(key, "").strip()
    if not value:
        raise ValueError(f"missing required value: {key}")
    return value


def _uuid(raw: dict, key: str, optional: bool = False) -> str | None:
    if optional and not raw.get(key, "").strip():
        return None
    try:
        return str(UUID(_required(raw, key)))
    except ValueError as exc:
        raise ValueError(f"invalid or missing UUID: {key}") from exc


def _date(raw: dict, key: str, optional: bool = False, timestamp: bool = False) -> Any:
    value = raw.get(key, "").strip()
    if not value and optional:
        return None
    try:
        if not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|T)", value):
            raise ValueError
        if timestamp:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else (parsed.astimezone(UTC))
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {key}") from exc


def _key(*values: Any) -> str:
    return hashlib.sha256(json.dumps(values, default=str).encode()).hexdigest()


def _parse(table: str, raw: dict) -> dict:
    if table == "patients":
        birth, death = _date(raw, "BIRTHDATE"), _date(raw, "DEATHDATE", optional=True)
        if death and death < birth:
            raise ValueError("DEATHDATE precedes BIRTHDATE")
        return dict(
            id=_uuid(raw, "Id"),
            birth_date=birth,
            death_date=death,
            gender=raw["GENDER"].strip() or "unknown",
            race=raw["RACE"].strip() or "unknown",
            ethnicity=raw["ETHNICITY"].strip() or "unknown",
        )
    patient = _uuid(raw, "PATIENT")
    code = _required(raw, "CODE")
    description = raw["DESCRIPTION"].strip() or "unknown"
    if table == "encounters":
        start = _date(raw, "START", timestamp=True)
        stop = _date(raw, "STOP", optional=True, timestamp=True)
        if stop and stop < start:
            raise ValueError("STOP precedes START")
        return dict(
            id=_uuid(raw, "Id"),
            patient_id=patient,
            start=start,
            stop=stop,
            encounter_class=raw["ENCOUNTERCLASS"].strip() or "unknown",
            code=code,
            description=description,
        )
    encounter = _uuid(raw, "ENCOUNTER", optional=True)
    if table == "conditions":
        start, stop = _date(raw, "START"), _date(raw, "STOP", optional=True)
        if stop and stop < start:
            raise ValueError("STOP precedes START")
        system = raw.get("SYSTEM", "").strip() or "SNOMED-CT"
        return dict(
            id=_key(patient, encounter, start, system, code),
            patient_id=patient,
            encounter_id=encounter,
            start=start,
            stop=stop,
            code=code,
            system=system,
            description=description,
        )
    when = _date(raw, "DATE", timestamp=True)
    value, kind = _required(raw, "VALUE"), _required(raw, "TYPE").lower()
    numeric = None
    if kind == "numeric":
        try:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError
        except ValueError as exc:
            raise ValueError("VALUE must be finite for numeric TYPE") from exc
    category = raw.get("CATEGORY", "").strip() or "unknown"
    units = raw["UNITS"].strip() or None
    return dict(
        id=_key(patient, encounter, when, code, category, value, units, kind),
        category=category,
        patient_id=patient,
        encounter_id=encounter,
        date=when,
        code=code,
        description=description,
        value=value,
        numeric_value=numeric,
        units=units,
        value_type=kind,
    )


def validate_export(directory: Path) -> ValidatedExport:
    """Validate a complete export, rejecting conflicts and invalid parent references.

    All references must resolve within the same export. Conflicting rows sharing a
    natural key are all rejected, so acceptance does not depend on input order.
    """
    result = ValidatedExport()
    sources: dict[str, list[tuple[int, dict]]] = {}
    for table, required in REQUIRED.items():
        path = directory / f"{table}.csv"
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle, strict=True)
                headers = reader.fieldnames or []
                missing = required - set(headers)
                if missing or len(headers) != len(set(headers)):
                    raise SchemaError(
                        f"{path.name}: missing {sorted(missing)} or duplicate headers"
                    )
                sources[table] = list(enumerate(reader, start=2))
        except (OSError, csv.Error, UnicodeError) as exc:
            raise SchemaError(f"Cannot read {path.name}: {exc}") from exc
    patients: dict[str, dict] = {}
    encounters: dict[str, dict] = {}
    for table in REQUIRED:
        result.input_counts[table] = len(sources[table])
        groups: dict[str, list[tuple[int, dict, dict]]] = {}
        for number, raw in sources[table]:
            try:
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError("CSV field count does not match header")
                row = _parse(table, raw)
                if table != "patients":
                    patient = patients.get(row["patient_id"])
                    if patient is None:
                        raise ValueError("PATIENT does not reference an accepted patient")
                    when = row.get("start", row.get("date"))
                    day = when.date() if isinstance(when, datetime) else when
                    if day < patient["birth_date"]:
                        raise ValueError("event precedes patient birth")
                    if patient["death_date"] and day > patient["death_date"]:
                        raise ValueError("event follows patient death")
                if table in ("conditions", "observations") and row["encounter_id"]:
                    encounter = encounters.get(row["encounter_id"])
                    if encounter is None or encounter["patient_id"] != row["patient_id"]:
                        raise ValueError("ENCOUNTER missing or belongs to another patient")
                groups.setdefault(row["id"], []).append((number, raw, row))
            except ValueError as exc:
                result.reject(table, number, raw, str(exc))
        accepted = []
        for group in groups.values():
            first = group[0][2]
            if any(row != first for _, _, row in group):
                for number, raw, _ in group:
                    result.reject(table, number, raw, "conflicting duplicate key")
                continue
            accepted.append(first)
            for number, raw, _ in group[1:]:
                result.reject(table, number, raw, "duplicate normalized row")
        result.rows[table] = accepted
        if table == "patients":
            patients = {r["id"]: r for r in accepted}
        elif table == "encounters":
            encounters = {r["id"]: r for r in accepted}
    return result
