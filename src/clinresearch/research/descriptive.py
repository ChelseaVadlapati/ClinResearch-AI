"""Patient-level descriptive summaries; uncertainty is conditional on synthetic data."""

import math

import numpy as np

from clinresearch.research.cohort import FEATURES


def describe(rows: list[dict]) -> dict:
    n = len(rows)
    positives = sum(row["readmission_30d"] for row in rows)
    fraction = positives / n if n else None
    interval = None
    reason = "Need >=20 patients and >=2 of each class for descriptive interval display."
    if n >= 20 and min(positives, n - positives) >= 2:
        z = 1.959963984540054
        denominator = 1 + z * z / n
        center = (fraction + z * z / (2 * n)) / denominator
        half = z * math.sqrt(fraction * (1 - fraction) / n + z * z / (4 * n * n)) / denominator
        interval, reason = [max(0.0, center - half), min(1.0, center + half)], None
    features = {}
    for name in FEATURES:
        values = [row[name] for row in rows if row.get(name) is not None]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Descriptive features must be finite and nonnegative")
        quantiles = np.quantile(values, [0, 0.25, 0.5, 0.75, 1]).tolist() if values else [None] * 5
        counts, edges = (
            np.histogram(
                values,
                bins=5,
                range=(min(values), max(values) if max(values) > min(values) else min(values) + 1),
            )
            if values
            else ([], [])
        )
        features[name] = {
            "observed": len(values),
            "missing": n - len(values),
            "minimum": quantiles[0],
            "q25": quantiles[1],
            "median": quantiles[2],
            "q75": quantiles[3],
            "maximum": quantiles[4],
            "histogram": [
                {"lower": float(edges[i]), "upper": float(edges[i + 1]), "count": int(count)}
                for i, count in enumerate(counts)
            ],
        }
    return {
        "patients": n,
        "positives": positives,
        "negatives": n - positives,
        "outcome_fraction": fraction,
        "outcome_wilson_95": interval,
        "interval_withheld_reason": reason,
        "features": features,
        "interpretation": "Synthetic sample only; not population or clinical inference.",
    }
