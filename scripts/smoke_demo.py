"""Verify the freshly loaded fixture demo using actual HTTP requests."""

import json
import os
from urllib.request import urlopen

base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")


def get(path: str) -> dict | list:
    """Read a JSON API response or fail on an HTTP error."""
    with urlopen(f"{base}{path}", timeout=10) as response:
        return json.load(response)


assert get("/health")["database"] == "ready"
summary = get("/cohort/summary?as_of=2025-01-01")
assert summary["counts"] == {"patients": 3, "encounters": 3, "conditions": 3, "observations": 3}
assert summary["age"]["median"] == 34
assert get("/encounters/monthly") == [
    {"month": "2024-01", "encounters": 2},
    {"month": "2024-02", "encounters": 0},
    {"month": "2024-03", "encounters": 1},
]
assert get("/conditions/common?limit=1")[0]["occurrences"] == 2
with urlopen(
    os.getenv("DASHBOARD_BASE_URL", "http://localhost:8501").rstrip("/") + "/_stcore/health",
    timeout=10,
) as response:
    assert response.read().decode() == "ok"
print("PASS: four API endpoints match fixture expectations; Streamlit health is ok.")
