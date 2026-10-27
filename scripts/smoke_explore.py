"""Check real fixture cohort filtering and aggregate-only downloads over HTTP."""

import json
import os
from urllib.error import HTTPError
from urllib.request import urlopen

base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
with urlopen(f"{base}/cohort/explore?gender=F&as_of=2025-01-01", timeout=10) as response:
    report = json.load(response)
assert report["summary"]["counts"] == {
    "patients": 1,
    "encounters": 2,
    "conditions": 2,
    "observations": 2,
}
with urlopen(f"{base}/cohort/explore?gender=F&download=true", timeout=10) as response:
    csv = response.read().decode()
assert "counts,patients,1" in csv and "patient_id" not in csv
try:
    urlopen(f"{base}/cohort/explore?minimum_age=80&maximum_age=20", timeout=10)
except HTTPError as exc:
    assert exc.code == 422
else:
    raise AssertionError("Invalid bounds accepted")
with urlopen(f"{base}/nlp/report", timeout=10) as response:
    nlp = json.load(response)
assert nlp["status"] in {"not_run", "available"}
if nlp["status"] == "available":
    assert "errors" not in nlp["report"]
print("PASS: cohort filters, safe aggregate CSV, invalid bounds and NLP endpoint")
