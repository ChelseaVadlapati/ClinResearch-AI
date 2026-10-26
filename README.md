# ClinResearch AI

A locally runnable **Synthetic EHR Research Analytics Platform**, built as a
biomedical research software portfolio project. It validates Synthea CSV exports,
loads normalized PostgreSQL tables, computes descriptive cohort summaries, and
serves a FastAPI API and Streamlit/Plotly dashboard.

**Synthetic data only. Not clinically validated. Not for diagnosis, treatment,
or real patient information.** This is an independent portfolio demonstration,
not a University of Florida product or an endorsed clinical system. There is no
prediction model or claimed model-performance metric.

## Quick demo with Docker Compose

Requires Docker Engine with Compose v2 and Python 3.11+ for the configuration and
smoke scripts. Run from the repository root:

```bash
python scripts/init_env.py
# Creates ignored .env with a random password; refuses to overwrite an existing file.
docker compose up --build -d --wait
python scripts/smoke_demo.py
```

The one-shot `ingest` service loads the tiny committed fixture, then the API and
dashboard start after readiness checks. The dashboard listens on port **8501**,
the API on **8000**, and interactive API documentation is at path `/docs` on the
API port. Ports are bound to the local machine only. Inspect with:

```bash
docker compose ps
docker compose logs ingest api dashboard
curl --fail 'http://localhost:8000/cohort/summary?as_of=2025-01-01'
```

Expected fixture results, verified by tests: **3 fictional patients, 3 encounters,
3 conditions, 3 observations**; encounter counts January/February/March 2024 are
**2/0/1**; two hypertension occurrences involve two distinct fixture patients;
median completed age at 2025-01-01 is **34**. These are hand-authored test-case
expectations, **not scientific findings or claims about a population**. All
numbers displayed in the dashboard are computed from the database.

```bash
# Reimport to verify idempotency; inspect reports/demo.json for zero new inserts.
docker compose run --rm ingest
# Stop services; retain demo data for next use.
docker compose down
# Optional destructive reset of this demo database only:
docker compose down -v
```

Use `.env.example` if configuring credentials manually. Keep passwords out of
source control and URL-encode special characters in database URLs (the setup
script generates URL-safe hex). Changing a password in `.env` does not change an
already initialized PostgreSQL volume's password. Reports and data are ignored.

### Builds behind a certificate proxy

Normal Docker builds use system certificate trust. In an environment with an
organization-provided CA bundle, supply it as a BuildKit secret without committing
it or disabling TLS verification:

```bash
docker build --secret id=custom_ca,src=/path/to/trusted-ca-bundle.pem -t clinresearch-ai:local .
docker compose up --no-build -d --wait
```

On hosts with read-only Docker configuration directories, set `BUILDX_CONFIG` to
a writable directory outside the checkout. The secret is used only for package
installation; it is not baked into image layers. Lockfile hashes remain enforced.

## Local Python development

Python 3.11+ and PostgreSQL 16 are the supported MVP targets. The lockfile was
resolved for Python 3.11 compatibility and includes development tools. No external
AI API keys or paid services are needed.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps -e .
python scripts/init_env.py  # skip if .env already exists
set -a; source .env; set +a
docker compose up -d --wait db
clinresearch ingest tests/fixtures/synthea --report reports/demo.json
uvicorn clinresearch.api.app:app --host 127.0.0.1 --port 8000
```

In another activated terminal, load `.env` and run:

```bash
set -a; source .env; set +a
streamlit run src/clinresearch/dashboard/app.py --server.address=127.0.0.1
```

Do not start local servers on ports already occupied by the Compose API/dashboard.
For an empty initialized schema use `clinresearch init-db`. `DATABASE_URL` is
required; it is never inferred from hard-coded credentials. SQLite is available
for lightweight tests (`DATABASE_URL=sqlite:///demo.db`), but PostgreSQL is the
reference database. Empty dashboards show a no-data message.

## Generate actual Synthea CSV exports

The committed CI fixture is hand-authored in Synthea's format. To generate a
larger synthetic cohort, install Java 17+ (Java 21 used during verification),
`curl`, and `sha256sum`, then run:

```bash
scripts/generate_synthea.sh "$PWD/data/synthea" 10
# In the activated Python environment with DATABASE_URL set:
clinresearch ingest data/synthea/csv --report reports/synthea.json
```

The script downloads the official Synthea **v3.3.0** release JAR over HTTPS,
verifies its pinned SHA-256, and refuses to overwrite an existing output folder.
It fixes patient/clinician seeds at **42**, reference date **2024-01-01**, end date
**2025-01-01**, locale and UTC timezone, Florida location, one generator thread,
and full-history CSV output. The source release corresponds to commit
`995cf2fd33e67918d4e33110d9f68ad248002221` in
[synthetichealth/synthea](https://github.com/synthetichealth/synthea/tree/v3.3.0).
Generation can produce deceased overflow records; the requested population is
not a promise about exported patient counts. Fixed inputs and the same generator
and Java runtime are needed for reproducibility.

The generated files remain under ignored `data/`. No real patient data or clinical
notes are included. Only four CSVs are ingested; Synthea may export other files.
Synthea can emit exact duplicate observations, which are reported as rejections.
An import exiting **2** means valid rows were committed but the rejection report
needs review; exit **1** indicates a structural/operational failure. Do not hide
these outcomes with `|| true`. See [validation rules](docs/validation.md).

For a clean generated cohort demo, use a separate database or explicitly reset
the disposable demo volume before ingestion. Upserts never delete rows missing
from later exports, so importing after the tiny fixture combines both cohorts.
The fixture-specific smoke script intentionally fails on a combined dataset.

## API

| Method/path | Computed response |
| --- | --- |
| `GET /health` | Database and expected-schema readiness; HTTP 503 if unavailable |
| `GET /cohort/summary?as_of=2025-01-01` | Counts, demographics, age statistics, latest import quality |
| `GET /encounters/monthly` | UTC month and encounter count, including gaps |
| `GET /conditions/common?limit=10` | Coding system/code, description, occurrence and distinct-patient counts |

`limit` accepts 1–100. Invalid dates/limits return 422. `as_of` affects ages only;
all records remain in the cohort. The API exposes aggregate data, not patient
records. Full definitions and architecture are in [docs/architecture.md](docs/architecture.md).

## Tests and lint

```bash
ruff check .
ruff format --check .
pytest -q                         # SQLite tests, no downloaded dataset required
# PostgreSQL tests use isolated random schemas, not shared-table deletion:
set -a; source .env; set +a
export TEST_DATABASE_URL="$DATABASE_URL"
pytest -q                         # exercises SQLite AND PostgreSQL
```

Tests cover missing schemas/files, invalid IDs/dates, rejection audit, duplicates,
parent/child joins, foreign keys, transactional rollback, repeated imports,
updates, empty data, aggregation, HTTP validation, and Streamlit rendering against
a live local API. GitHub Actions runs lint and tests with PostgreSQL on Python
3.11 and 3.12. Local execution does not establish that hosted CI has run.

To intentionally update dependencies, use `uv pip compile pyproject.toml --extra dev
--python-version 3.11 --generate-hashes -o requirements.lock`, then reinstall and
rerun checks. Do not edit dependency hashes to bypass verification.

## Project layout

```text
src/clinresearch/
  ingestion/         CSV validation and rejection accounting
  database/          normalized SQLAlchemy models, sessions, atomic loader
  transformations/   Pandas/SQL descriptive summaries
  api/               FastAPI endpoints and Pydantic response contracts
  dashboard/         Streamlit UI with Plotly charts
  cli.py             schema creation and import commands
tests/fixtures/      tiny deterministic, fully fictional CSV dataset
docs/               implementation plan, architecture, validation rules
scripts/            local configuration, pinned Synthea generation, HTTP smoke check
```

## Limitations and next steps

Synthetic records do not establish clinical validity, representativeness,
equity, or transportability to any real population. This project does not infer
clinical conclusions, predict outcomes, or claim that synthetic text is a real
clinical note. Frequencies are descriptive software outputs, not epidemiologic
estimates. Review missingness and rejected rows before interpreting any summary.

The MVP is intentionally bounded: complete-file ingestion in memory, simple
upserts, no migrations, no terminology service or clinical range checks, and no
authentication or production deployment hardening. Future work could add schema
migrations, streaming ingestion, study-specific cohort definitions, and access
controls after requirements and tests are established. See
[verification evidence](docs/verification.md) for what was actually run.
