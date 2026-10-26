# Phase 1 implementation plan

1. Establish an installable Python package and reproducible dependency lock.
2. Validate four Synthea CSVs before loading: explicit schemas, canonical identifiers,
   required values, ISO dates, duplicate conflicts, cross-table references, and rejection audit.
3. Load normalized patient, encounter, condition, and observation tables atomically;
   persist import runs and rejection metadata; support idempotent refresh by stable keys.
4. Compute demographics, encounter months, condition counts, and ingestion quality
   from database records. Define denominators, dates, and limitations.
5. Serve typed FastAPI responses and an API-backed Streamlit/Plotly dashboard.
6. Exercise deterministic fixtures, invalid inputs, joins, repeated loads, API contracts,
   and PostgreSQL integration. Provide Docker Compose and GitHub Actions.
7. Document tested demo commands, Synthea generation, architecture, and limitations;
   commit on a feature branch and prepare a PR.

No prediction model, clinical validation, real patient data, or inferred scientific
findings are in scope. SQLite is a fast unit-test backend; PostgreSQL integration
must be tested separately. Invalid rows must be logged and represented in reports.
