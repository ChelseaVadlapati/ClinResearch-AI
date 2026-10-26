"""Read-only smoke check for the saved fixture research report."""

import json
import os
from urllib.request import urlopen

base = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
with urlopen(f"{base}/research/report", timeout=10) as response:
    result = json.load(response)
assert result["status"] == "available"
report = result["report"]
assert report["synthetic_only"] is True
assert report["evaluation"]["status"] == "insufficient_data"
assert "metrics" not in report["evaluation"]
assert "model" not in report["evaluation"]
assert report["cohort_audit"]["eligible_patients"] == 0
assert sum(r["count"] for r in report["cohort_flow"] if r["unit"] == "record") == 3
print("PASS: fixture research flow reconciles; insufficient_data retained without scores.")
