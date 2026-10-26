# Verification evidence

Executed in the development environment on 2026-10-26. These are software
validation results, not clinical validation or scientific findings.

- Ruff lint and formatting checks passed.
- Python 3.11 and 3.12: 41 pytest cases passed on each version with both SQLite
  and PostgreSQL 16 enabled.
  These include the Streamlit AppTest harness talking to a live FastAPI server.
- A Docker image built successfully with hash-verified locked packages. This
  environment required its trusted CA bundle passed via the documented optional
  BuildKit secret; TLS verification remained enabled.
- `docker compose up -d --no-build --wait` completed: PostgreSQL, FastAPI and
  Streamlit health checks passed, and the one-shot fixture importer exited 0.
- `python scripts/smoke_demo.py` passed against running Compose services, checking
  actual responses from all four API routes and the Streamlit health endpoint.
- Reimporting the fixture returned zero inserts and zero updates for all four
  data tables while recording another audit run. The HTTP smoke check still passed.
- Official Synthea v3.3.0 ran twice on Java 21 with population argument 2 and the
  script's fixed configuration. All four CSV files were byte-identical between
  runs. Actual input rows: 2 patients, 545 encounters, 294 conditions, 7,793
  observations. Validation accepted 7,786 observations and reported 7 exact
  normalized duplicates. These counts describe this verification sample only.
- The generated sample was loaded into a temporary isolated PostgreSQL schema,
  then reloaded with zero new inserts/updates. Stored counts and rejection audit
  matched the validator; the temporary schema was removed afterward.
- GitHub Actions is configured; no hosted CI result is claimed here.

An upstream Starlette warning recommends replacing its httpx TestClient transport
in the future. It did not prevent any test from executing or passing.

Synthea repeated-run SHA-256 values:

```text
patients.csv      d1f9eb8bb86ed10958b8c8abae98dc0a977c3b6b446576d72e62bad0d8fc8440
encounters.csv    efc8b6039989ee7c005db07911718bed0f7c3919cd73eb9a24fd4e56e2d9cbb9
conditions.csv    c058c762477c4f797d0255c6819909b3f3a63ef7fa0d9032f9788bb743444f61
observations.csv  c9c7b3caff1e152c5019128c3c9c5e4e8048f575b7470cbd8552493981560f1b
```

To reproduce automated checks, follow the README's PostgreSQL test commands.
To repeat generator verification, use two new output directories with population
argument 2 and compare the four CSVs. Do not overwrite existing outputs.
