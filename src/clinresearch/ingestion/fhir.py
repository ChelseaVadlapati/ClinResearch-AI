"""Audited, offline FHIR R4 subset; references are never fetched from the network."""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from clinresearch.ingestion.csv import SchemaError, ValidatedExport, _parse

TABLES = {
    "Patient": "patients",
    "Encounter": "encounters",
    "Condition": "conditions",
    "Observation": "observations",
    "MedicationRequest": "medication_requests",
}
CLASSES = {
    "IMP": "inpatient",
    "AMB": "ambulatory",
    "EMER": "emergency",
    "OBSENC": "observation",
    "VR": "virtual",
    "HH": "home health",
}


def required(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {label}")
    return value.strip()


def timestamp(value):
    value = required(value, "timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if "T" not in value or parsed.tzinfo is None:
        raise ValueError("timestamp requires time and timezone")
    return parsed.astimezone(UTC)


def day(value):
    value = required(value, "date")
    return timestamp(value).date() if "T" in value else date.fromisoformat(value)


def coding(value):
    codes = value.get("coding") if isinstance(value, dict) else None
    if not isinstance(codes, list) or not codes:
        raise ValueError("coded concept requires coding system and code")
    for code in codes:
        if not isinstance(code, dict):
            raise ValueError("invalid coding")
        system = required(code.get("system"), "coding system")
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", system):
            raise ValueError("coding system must be a URI")
        required(code.get("code"), "code")
    selected = sorted(codes, key=lambda c: (c["system"], c["code"]))[0]
    return (
        selected["system"],
        selected["code"],
        selected.get("display") or value.get("text") or "unknown",
    )


def identifier(dataset, kind, resource_id):
    return str(uuid5(NAMESPACE_URL, json.dumps([dataset, kind, resource_id])))


def validate_fhir(path: Path, dataset: str) -> ValidatedExport:
    """Validate a complete synthetic dataset before any database writes.

    FullUrl and Type/id references resolve only against this import. Conflicting
    resource identities are all rejected; exact duplicates are audited. Dataset
    version is a stable namespace, not a per-run timestamp. Unsupported resource
    types are counted separately. This is not full FHIR profile validation.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", dataset):
        raise SchemaError("dataset must be a stable version label of 1-100 safe characters")
    paths = sorted(path.glob("*.json")) if path.is_dir() else [path]
    if not paths:
        raise SchemaError("No FHIR JSON files found")
    entries, hashes = [], {}
    try:
        for source in paths:
            payload = source.read_bytes()
            hashes[source.name] = hashlib.sha256(payload).hexdigest()
            document = json.loads(payload)
            if not isinstance(document, dict):
                raise ValueError("FHIR document must be an object")
            if document.get("resourceType") == "Bundle":
                if document.get("type") not in {"collection", "transaction", "batch", "document"}:
                    raise ValueError(
                        "unsupported Bundle type (history/response semantics not imported)"
                    )
                members = document.get("entry", [])
                if not isinstance(members, list):
                    raise ValueError("Bundle entry must be a list")
            else:
                members = [{"resource": document}]
            for member in members:
                if not isinstance(member, dict) or not isinstance(member.get("resource"), dict):
                    raise ValueError("Bundle entry requires resource object")
                entries.append((source.name, member.get("fullUrl"), member["resource"]))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SchemaError("Malformed or unreadable FHIR document; nothing loaded") from exc

    result = ValidatedExport(
        rows={t: [] for t in TABLES.values()}, input_counts={t: 0 for t in TABLES.values()}
    )
    groups, aliases = defaultdict(list), defaultdict(set)
    skipped = Counter()
    for number, (source, full_url, resource) in enumerate(entries, 1):
        kind = resource.get("resourceType")
        if not isinstance(kind, str) or kind not in TABLES:
            skipped[str(kind)] += 1
            continue
        table = TABLES[kind]
        result.input_counts[table] += 1
        raw = {"source_file": source, "resource": resource}
        try:
            rid = required(resource.get("id"), "resource id")
            if not re.fullmatch(r"[A-Za-z0-9.-]{1,64}", rid):
                raise ValueError("invalid FHIR logical id")
            identifiers = resource.get("identifier", [])
            if not isinstance(identifiers, list):
                raise ValueError("identifier must be a list")
            for item in identifiers:
                required(item.get("system"), "identifier system")
                required(item.get("value"), "identifier value")
            if full_url is not None:
                required(full_url, "fullUrl")
            key = (kind, rid)
            groups[key].append((number, raw))
            aliases[f"{kind}/{rid}"].add(key)
            if full_url is not None:
                aliases[required(full_url, "fullUrl")].add(key)
        except (ValueError, TypeError, AttributeError) as exc:
            result.reject(table, number, raw, str(exc))
    conflicted = {
        key
        for key, group in groups.items()
        if any(raw["resource"] != group[0][1]["resource"] for _, raw in group)
    }
    conflicted.update(key for keys in aliases.values() if len(keys) > 1 for key in keys)
    accepted = {}

    def reference(value, kind, optional=False):
        if value is None and optional:
            return None
        ref = required(value.get("reference") if isinstance(value, dict) else None, "reference")
        keys = aliases.get(ref, set())
        if len(keys) != 1:
            raise ValueError("missing or ambiguous local reference")
        key = next(iter(keys))
        if key[0] != kind or key not in accepted:
            raise ValueError("reference has wrong type or rejected parent")
        return accepted[key]

    for kind, table in TABLES.items():
        for key in sorted(k for k in groups if k[0] == kind):
            group = groups[key]
            if key in conflicted:
                for number, raw in group:
                    result.reject(table, number, raw, "conflicting resource identity or fullUrl")
                continue
            number, raw = group[0]
            resource = raw["resource"]
            try:
                normalized_id = identifier(dataset, *key)
                if kind == "Patient":
                    gender = resource.get("gender", "unknown")
                    if gender not in {"female", "male", "other", "unknown"}:
                        raise ValueError("invalid administrative gender")
                    if resource.get("deceasedBoolean") is True:
                        raise ValueError("death flag without date cannot establish follow-up")
                    row = _parse(
                        "patients",
                        {
                            "Id": normalized_id,
                            "BIRTHDATE": day(resource.get("birthDate")).isoformat(),
                            "DEATHDATE": day(resource["deceasedDateTime"]).isoformat()
                            if resource.get("deceasedDateTime")
                            else "",
                            "GENDER": {"female": "F", "male": "M"}.get(gender, gender),
                            "RACE": "unknown",
                            "ETHNICITY": "unknown",
                        },
                    )
                else:
                    person = reference(resource.get("subject"), "Patient")
                    common = {"PATIENT": person["id"], "Id": normalized_id}
                    if kind == "Encounter":
                        if resource.get("status") not in {"finished", "in-progress"}:
                            raise ValueError("unsupported encounter status")
                        classification = resource.get("class", {})
                        if (
                            classification.get("system")
                            != "http://terminology.hl7.org/CodeSystem/v3-ActCode"
                        ):
                            raise ValueError("encounter class requires R4 ActCode system")
                        if classification.get("code") not in CLASSES:
                            raise ValueError("unsupported encounter class")
                        period = resource.get("period", {})
                        start = timestamp(period.get("start"))
                        stop = timestamp(period["end"]) if period.get("end") else None
                        if resource["status"] == "finished" and stop is None:
                            raise ValueError("finished encounter requires period.end")
                        types = resource.get("type", [])
                        _, code, description = coding(types[0] if types else None)
                        row = _parse(
                            table,
                            {
                                **common,
                                "START": start.isoformat(),
                                "STOP": stop.isoformat() if stop else "",
                                "CODE": code,
                                "DESCRIPTION": description,
                                "ENCOUNTERCLASS": CLASSES[classification["code"]],
                            },
                        )
                    else:
                        encounter = reference(resource.get("encounter"), "Encounter", optional=True)
                        if encounter and encounter["patient_id"] != person["id"]:
                            raise ValueError("encounter belongs to another patient")
                        common["ENCOUNTER"] = encounter["id"] if encounter else ""
                        concept = (
                            resource.get("medicationCodeableConcept")
                            if kind == "MedicationRequest"
                            else resource.get("code")
                        )
                        system, code, description = coding(concept)
                        common.update(CODE=code, DESCRIPTION=description, SYSTEM=system)
                        if kind == "Condition":
                            onset = day(resource.get("onsetDateTime"))
                            row = _parse(
                                table,
                                {
                                    **common,
                                    "START": onset.isoformat(),
                                    "STOP": day(resource["abatementDateTime"]).isoformat()
                                    if resource.get("abatementDateTime")
                                    else "",
                                },
                            )
                        elif kind == "Observation":
                            if resource.get("status") not in {"final", "amended", "corrected"}:
                                raise ValueError("unsupported observation status")
                            value_keys = [k for k in resource if k.startswith("value")]
                            if len(value_keys) != 1:
                                raise ValueError(
                                    "one supported value[x] required; "
                                    "components/absent values not flattened"
                                )
                            field = value_keys[0]
                            value, units, value_type = resource[field], "", "text"
                            if field == "valueQuantity":
                                quantity = value
                                value = quantity.get("value")
                                if (
                                    isinstance(value, bool)
                                    or not isinstance(value, (float, int))
                                    or not math.isfinite(value)
                                ):
                                    raise ValueError("quantity must be finite numeric")
                                units = quantity.get("code") or quantity.get("unit") or ""
                                if quantity.get("comparator"):
                                    raise ValueError(
                                        "bounded quantities cannot be treated as exact values"
                                    )
                                value_type = "numeric"
                            elif field == "valueCodeableConcept":
                                _, value, _ = coding(value)
                            elif field == "valueBoolean":
                                if type(value) is not bool:
                                    raise ValueError("invalid boolean value")
                            elif field != "valueString" or not isinstance(value, str):
                                raise ValueError("unsupported observation value type")
                            categories = resource.get("category", [])
                            category = coding(categories[0])[1] if categories else "unknown"
                            row = _parse(
                                table,
                                {
                                    **common,
                                    "DATE": timestamp(
                                        resource.get("effectiveDateTime")
                                    ).isoformat(),
                                    "VALUE": str(value),
                                    "UNITS": units,
                                    "TYPE": value_type,
                                    "CATEGORY": category,
                                },
                            )
                        else:
                            if resource.get("status") not in {
                                "active",
                                "completed",
                                "stopped",
                                "cancelled",
                                "on-hold",
                                "draft",
                                "unknown",
                            }:
                                raise ValueError("unsupported medication request status")
                            if resource.get("intent") not in {
                                "proposal",
                                "plan",
                                "order",
                                "original-order",
                                "reflex-order",
                                "filler-order",
                                "instance-order",
                                "option",
                            }:
                                raise ValueError("invalid medication request intent")
                            row = dict(
                                id=normalized_id,
                                patient_id=person["id"],
                                encounter_id=encounter["id"] if encounter else None,
                                authored_on=timestamp(resource.get("authoredOn")),
                                system=system,
                                code=code,
                                description=description,
                                status=resource["status"],
                                intent=resource["intent"],
                            )
                    when = row.get("start", row.get("date", row.get("authored_on")))
                    event_day = when.date() if isinstance(when, datetime) else when
                    if event_day < person["birth_date"] or (
                        person["death_date"] and event_day > person["death_date"]
                    ):
                        raise ValueError("event outside patient lifetime")
                resource_hash = hashlib.sha256(
                    json.dumps(resource, sort_keys=True, allow_nan=False).encode()
                ).hexdigest()
                row["id"] = normalized_id
                accepted[key] = row
                result.rows[table].append(row)
                result.rows.setdefault("fhir_resources", []).append(
                    dict(
                        id=normalized_id,
                        dataset=dataset,
                        resource_type=kind,
                        resource_id=key[1],
                        source_file=raw["source_file"],
                        sha256=resource_hash,
                        identifiers=resource.get("identifier", []),
                        coding=_all_coding(resource),
                        normalized_table=table,
                        normalized_id=normalized_id,
                    )
                )
            except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
                result.reject(table, number, raw, str(exc))
                for duplicate_number, duplicate_raw in group[1:]:
                    result.reject(
                        table, duplicate_number, duplicate_raw, "duplicate of rejected resource"
                    )
                continue
            for duplicate_number, duplicate_raw in group[1:]:
                result.reject(table, duplicate_number, duplicate_raw, "duplicate resource")
    result.metadata = {
        "format": "FHIR R4 supported subset",
        "dataset": dataset,
        "synthetic_only": True,
        "files_sha256": hashes,
        "resources_total": len(entries),
        "unsupported_resource_counts": dict(sorted(skipped.items())),
    }
    return result


def _all_coding(resource):
    """Preserve coding systems even where the original CSV schema lacks a column."""
    if isinstance(resource, dict):
        found = [resource] if "system" in resource and "code" in resource else []
        return found + [c for value in resource.values() for c in _all_coding(value)]
    if isinstance(resource, list):
        return [c for value in resource for c in _all_coding(value)]
    return []
