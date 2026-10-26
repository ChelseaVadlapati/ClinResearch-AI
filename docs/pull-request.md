# Add synthetic EHR research analytics MVP

The repository now supports a complete synthetic research demo: validated Synthea
CSV ingestion, normalized PostgreSQL storage, descriptive cohort summaries,
FastAPI endpoints, and an API-backed Streamlit/Plotly dashboard. Invalid records
are logged and retained in JSON/database rejection audits; repeated imports leave
clinical-style row counts unchanged.

Includes a deterministic fictional CI fixture, hash-locked Python dependencies,
Docker Compose, GitHub Actions, fixed-seed Synthea generation, and setup and
research-limitations documentation. There are no real patient records, prediction
metrics, or claims of clinical validation.

Validation: Ruff checks; 41 tests on each of Python 3.11 and 3.12 with SQLite and PostgreSQL;
Docker build/startup and all four endpoint smoke checks; Streamlit rendering
against a live API; two byte-identical fixed-configuration Synthea exports and a
PostgreSQL import/reimport of the generated sample. See docs/verification.md.

Limitations: in-memory full-export ingestion, no schema migrations or production
access controls, no clinical terminology/plausibility validation. Hosted CI status
must be checked separately after push.
