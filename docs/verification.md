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

## Milestone 2 verification — 2026-10-26

- Python 3.11.17 and 3.12.14: **69 tests passed on each version**, with SQLite and
  isolated PostgreSQL schemas enabled. Includes three dashboard report states,
  the CLI, temporal purging, future-record invariance, and training-only scaling.
- Ruff lint/format and whitespace checks passed. The updated hash lock installed
  on both Python versions. The existing Starlette TestClient deprecation warning
  remains non-blocking.
- Updated Docker image built; PostgreSQL, API, and dashboard became healthy.
  Existing HTTP smoke checks passed, and `/research/report` returned the saved
  fixture analysis with `insufficient_data`. The fixture has no eligible inpatient
  index discharges; no scores or notes were invented.
- Synthea v3.3.0 generated population argument 200 with the script's fixed seeds,
  dates, and locale. Export contained 234 patients (including deceased overflow),
  48,198 encounters, 25,272 conditions, and 646,413 observations. The validator
  rejected 116 exact normalized observation duplicates, accepting 646,297.
  Import exited 2 as documented; all rejection reasons were inspected. This run
  used a separate SQLite database and did not alter the PostgreSQL demo cohort.
- The generated cohort, using observation end 2025-01-01 and a preselected split
  date 2010-01-01, yielded 122 eligible patients and 122 labeled simulated notes.
  There was only **one** positive outcome: train 82 patients/1 positive, test
  39/0, and 1 purged patient. The evaluator correctly withheld model fitting and
  metrics. This is insufficient for a meaningful readmission evaluation.
- The fitting, baseline comparison, metrics, calibration bins, and seeded
  bootstrap paths were exercised using a deliberately constructed 40-patient
  software fixture. This verifies executable code, **not research performance**.
  No trained model validated on a sufficiently powered Synthea cohort is claimed.

Generated files remain under ignored `data/research-validation/`; the default
Docker demo report is under ignored `reports/research/`. Generated records and
model artifacts are not committed. Hosted CI is a separate check after push.


## PR review verification — 2026-10-26 (America/New_York)

Reviewed the existing feature branch without rebuilding an application image or
removing existing database volumes. Corrected Ruff failures, inconsistent saved
flow/date validation, CLI database/output failure handling, and the source-mounted
Streamlit startup error (`global.developmentMode` inferred from `/deps`).
Browser inspection also found internal API requests being sent through the proxy;
Compose now excludes its internal API hostname via `NO_PROXY`. CI checks this
connection from inside the dashboard container.

- Ruff check and format check passed.
- Python 3.12.14 with PostgreSQL 16 and SQLite: **115 passed, 1 skipped**.
  The skip is the intentionally SQLite-only legacy constraint-bypass fixture.
  The existing Starlette transport deprecation warning remains.
- Isolated source-mounted Compose PostgreSQL, API and dashboard health checks
  passed without an application image build. Both `scripts/smoke_demo.py` and
  `scripts/smoke_research.py` passed. Dependency installation in this environment
  used a read-only trusted CA mount and `PIP_CERT`, with hash and TLS checks enabled.
- Actual dashboard screenshots are in `docs/images/`; fixture aggregate flow is
  in `docs/demo-cohort-flow.csv`. No real patient data is used by these demos.
- Reanalyzed the available generated export (`data/synthea-validation/csv`):
  2 patients, 545 encounters, 294 conditions, 7,793 input observations (7 duplicate
  rejections). There was 1 eligible index and **0 positive outcomes**, with split
  2010-01-01 and observation end 2025-01-01. Status remained `insufficient_data`.
  This verification used a separate temporary SQLite database.
- The previously documented 234-patient export is absent from this workspace.
  Its historical one-positive result was not independently rerun in this review.
  Neither available evidence nor that historical result supports model evaluation.

Exact local checks after installing the locked dependencies:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
set -a; source .env; set +a
TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/pytest -q
```

Compose reproduction commands are in README under “Reproduce without rebuilding
the application image.” Hosted Actions results are recorded in PR #1; the prior
head failed lint and Streamlit startup, and this revision addresses both failures.

## Portfolio milestone 1 — FHIR R4 (2026-10-27)

Baseline latest main: `4e41f67`, PR #1 already merged externally. Baseline was
115 passed/1 skipped with SQLite/PostgreSQL; Ruff lint and format passed.
Implemented the supported FHIR subset and additive Alembic revisions on
`feat/fhir-r4-integration`; preserved the CSV schema and API behavior.

Validation after adding FHIR and live-dashboard regressions: **135 passed,
1 skipped** on Python 3.12, SQLite + PostgreSQL 16. The skip remains the legacy
SQLite-specific constraint bypass. Ruff lint/format and git diff whitespace pass.
Existing Compose API/dashboard and research smoke scripts pass after migration;
the first immediate-after-restart check encountered a connection reset, then
passed after waiting for container health. FHIR CLI fixture import and repeat
import pass in a separate SQLite database; repeat has zero inserts/updates for
all six normalized/provenance tables. Tests render both CSV and FHIR data through
a live FastAPI server and Streamlit AppTest. No application image was rebuilt.

Fresh official Synthea v3.3.0 paired CSV/FHIR generation (Java 21, population 2,
seed 42, existing fixed dates) produced 2 patients. FHIR validation accepted
2 patients, 545 encounters, 294 conditions, 5,031 observations and 419 medication
requests. All 245 rejected supported records were component-only/absent-value
observations, a documented unsupported shape. Other resource types are separately
counted as unsupported. CSV has 7,793 input observations (7 duplicate rejections);
CSV flattens data differently, so observation counts are not equivalent. No
FHIR-to-CSV scientific equivalence or clinical validity is claimed.

Commands (activate the locked environment first):

```bash
ruff check .
ruff format --check .
set -a; source .env; set +a
TEST_DATABASE_URL="$DATABASE_URL" pytest -q
scripts/generate_synthea.sh "$PWD/data/fhir-verification" 2 both
DATABASE_URL=sqlite:///fhir-demo.db clinresearch ingest-fhir \
  tests/fixtures/fhir/bundle.json --dataset fictional-v1 --synthetic-only \
  --report reports/fhir-demo.json
export COMPOSE_PROJECT_NAME=clinresearch-review
export COMPOSE_FILE=docker-compose.yml:docker-compose.ci.yml
docker compose up --no-build -d --wait
python scripts/smoke_demo.py
python scripts/smoke_research.py
```

Choose a fresh generation/output directory when reproducing. The actual paired
export is ignored under `data/fhir-verification`. Hosted CI evidence is linked
in the milestone PR; later milestones must not start until that check passes.

Milestone 1 hosted gate: [Actions run 40536007024](https://github.com/ChelseaVadlapati/ClinResearch-AI/actions/runs/40536007024)
passed Python 3.11/3.12 PostgreSQL tests and Compose smoke on `88c9024`.
Milestone 2 starts on a stacked branch from milestone 1; neither PR is auto-merged.

## Portfolio milestone 2 — versioned research cohorts (2026-10-27)

Stacked on milestone 1. Versioned configuration preserves the 30-day endpoint,
365-day lookback and seed while allowing adult age bounds, index date windows and
stricter class/sample gates. Windows filter indices, not lookback/outcome records.
Added reconciled exclusions, config hash, complete saved config, descriptive
quartiles/histograms, class counts and conditional Wilson intervals. Added data
dictionary, model card and protocol updates; no additional model is justified.

Python 3.12 with SQLite/PostgreSQL: **147 passed, 1 skipped** (same SQLite-only
case). Ruff lint/format passed. Live API/Streamlit regressions pass. Compose config
analysis in fresh `reports/m2-config` returns zero eligible fixture indices and
`insufficient_data`, with no model or metrics. Existing CSV/API/dashboard and
research smoke checks remain required. No scientific performance is inferred.

```bash
ruff check .
ruff format --check .
set -a; source .env; set +a
TEST_DATABASE_URL="$DATABASE_URL" pytest -q
docker compose run --rm --no-deps ingest python -m clinresearch.cli analyze \
  --observation-end 2025-01-01 --split-date 2024-01-01 \
  --config configs/adult-return-v1.json --output /app/reports/m2-config
python scripts/smoke_demo.py
python scripts/smoke_research.py
```

Use README's source-mounted Compose configuration and a new output directory.
The example requires 100 patients and 20 of each class per partition, not a power
calculation. No-config behavior retains historical 10/2 software guardrails.
Descriptive Wilson intervals are withheld below 20 patients or 2 of either class.
Clinical validity, outside-care completeness and recording-time availability remain
unestablished. Hosted CI is checked in the milestone PR before proceeding.

Milestone 2 hosted gate: [Actions run 40537160134](https://github.com/ChelseaVadlapati/ClinResearch-AI/actions/runs/40537160134)
passed all Python/PostgreSQL and Compose jobs on `3a10e38` before NLP work began.

## Portfolio milestone 3 — experimental CPU NLP (2026-10-27)

Preserved the deterministic extractor and created a separate 48-train/24-test
synthetic assertion benchmark. The assistant authored labels independently of the
note template/extractor; there is no independent human/clinical review. Pinned
Apache-2.0-declared MiniLM revision and asset SHA-256 values, with optional CPU
ONNX/tokenizer dependencies constrained to the application's base lock versions.
No NLP information is added to inpatient-return features.

Python 3.12 SQLite/PostgreSQL suite: **152 passed, 1 skipped**. Ruff lint/format
passed; five NLP-focused regressions also rerun after input-contract hardening.
Compose API/dashboard/research smoke and baseline-only NLP command passed.
Actual frozen MiniLM inference ran on CPU with fixed logistic head and produced
the committed `benchmarks/nlp/verified-results-v1.json`; offline rerun was
byte-identical. The first attempt could not write to root-owned Compose reports;
it was rerun successfully to a fresh writable data directory. No missing run was
substituted with fabricated predictions.

Exact transformer reproduction and optional environment commands are in
`docs/nlp-evaluation.md`. Actual holdout macro F1: rules 0.5984848485, TF-IDF
0.7892857143, MiniLM 0.7641025641. These are tiny synthetic software-benchmark
results, not clinical accuracy, model superiority or real-world validation.
All 10 rule errors and 5 errors for each learned classifier are retained. Exact
rule spans matched 24/24 controlled-vocabulary snippets, not general clinical NLP.

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
set -a; source .env; set +a
TEST_DATABASE_URL="$DATABASE_URL" .venv/bin/pytest -q
.venv-nlp/bin/python -m clinresearch.nlp.benchmark --output data/nlp-verification-v1 \
  --model-lock benchmarks/nlp/model-lock.json --cache data/models/minilm-v1 --download-model
.venv-nlp/bin/python -m clinresearch.nlp.benchmark --output data/nlp-verification-repeat \
  --model-lock benchmarks/nlp/model-lock.json --cache data/models/minilm-v1
cmp data/nlp-verification-v1/report.json data/nlp-verification-repeat/report.json
python scripts/smoke_demo.py
python scripts/smoke_research.py
```

Use fresh output paths. Hosted CI includes a separate pinned CPU NLP job and
archives its computed report, alongside existing lint/tests/Compose checks.
