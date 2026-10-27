"""Transparent template simulation and a bounded, sentence-scoped concept extractor."""

import re

LABEL = "SIMULATED NOTE — generated from synthetic structured data; not a clinical record."
# Small, auditable vocabulary; deliberately not a general clinical NLP system.
CONCEPTS = {
    "hypertension": r"\b(?:hypertension|high blood pressure)\b",
    "diabetes": r"\b(?:diabetes(?: mellitus)?|type [12] diabetes)\b",
    "heart_failure": r"\b(?:congestive heart failure|heart failure)\b",
    "copd": r"\b(?:copd|chronic obstructive pulmonary disease)\b",
    "asthma": r"\basthma\b",
    "kidney_disease": r"\b(?:chronic kidney disease|ckd)\b",
}


def extract_concepts(text: str) -> list[dict]:
    """Return mention offsets and conservative assertion labels, not diagnoses.

    Any negation/uncertainty/family cue in a sentence scopes the entire sentence.
    This intentionally favors auditable rules over unsupported clinical accuracy.
    """
    mentions = []
    for sentence in re.finditer(r"[^.!?\n]+", text):
        value = sentence.group()
        if re.search(r"\b(?:family history|mother|father|sibling)\b", value, re.I):
            assertion = "family"
        elif re.search(r"\b(?:no|denies|without|negative for|not)\b", value, re.I):
            assertion = "negated"
        elif re.search(r"\b(?:possible|suspected|rule out|may have)\b", value, re.I):
            assertion = "uncertain"
        else:
            assertion = "present"
        for concept, pattern in CONCEPTS.items():
            for match in re.finditer(pattern, value, re.I):
                mentions.append(
                    {
                        "concept": concept,
                        "assertion": assertion,
                        "text": match.group(),
                        "start": sentence.start() + match.start(),
                        "end": sentence.start() + match.end(),
                    }
                )
    return sorted(mentions, key=lambda mention: (mention["start"], mention["concept"]))


def simulate_note(row: dict) -> dict:
    """Only use information available at index discharge; never include the outcome."""
    # Emit controlled concept names rather than inserting unconstrained descriptions.
    concepts = sorted(
        {
            mention["concept"]
            for description in row["known_conditions"]
            for mention in extract_concepts(description)
            if mention["assertion"] == "present"
        }
    )
    lines = [
        LABEL,
        f"Synthetic discharge summary. Age: {row['age']} years.",
        f"Length of stay: {row['length_of_stay_days']:.2f} days.",
    ]
    names = {"kidney_disease": "chronic kidney disease"}
    lines += [
        f"Documented history: {names.get(concept, concept.replace('_', ' '))}."
        for concept in concepts
    ]
    if not concepts:
        lines.append("No vocabulary-matched conditions documented; absence is not exclusion.")
    text = "\n".join(lines)
    return {
        "synthetic_only": True,
        "template_version": "1",
        "patient_id": row["patient_id"],
        "encounter_id": row["encounter_id"],
        "available_at": row["discharge"],
        "text": text,
        "concepts": extract_concepts(text),
    }
