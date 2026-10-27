# Portfolio integration verification — 2026-10-27

## Ancestry and preservation

Inspected remote branches, PR metadata, commit graph and file diffs before editing.
Main was `d0d9adc` (PR #2). PR #3 merged into feat/fhir-r4-integration (`cd5766e`),
#4 into feat/versioned-research-cohorts (`8696c9d`), #5 into feat/experimental-nlp
(`4987f9d`), and #6 into feat/research-dashboard (`3f35d93`). Thus merged status
alone did not put the later milestones on main.

Created integration/portfolio-main from origin/main and merged those four remote
branches in order, preserving both implementation and PR merge ancestry. All
merges were conflict-free. Before documentation edits, the resulting Git tree was
identical to milestone 5 (`840c139`). No migrations, configuration, tests, benchmark
JSON, NLP fixtures/model lock, scripts or application files were discarded or
rewritten. Existing main is an ancestor. No force pushes or automatic main merge.

The integration adds the 55-file milestone delta to main; this verification file
is the 56th changed file. Only README.md and this file differ from the previously
verified final milestone tree. README now explains new/existing main checkouts,
the temporary review branch, and the three-patient default; its optional destructive
volume-reset example was removed. Detailed file inventory follows below.

## Actual verification

- Ruff check and format: passed, 67 Python files already formatted.
- Full Python 3.12 SQLite + PostgreSQL suite: **178 passed, 1 skipped**, 33.87 s.
  The intentional skip is the SQLite-only legacy constraint bypass fixture when
  parametrized for PostgreSQL. Existing Starlette TestClient deprecation warning.
- Initial attempt against stopped historical port 5432: 124 passed, 55 connection
  setup errors. Reran against the new integration PostgreSQL on port 25432 with
  the passing result above; no application defect or test suppression.
- One-command demo: passed in separate `clinresearch-integration` project using
  ports 25432/28000/28501. Readiness, smoke_demo.py, smoke_research.py and
  smoke_explore.py passed. Artifacts: reports/demo-ac92a51f57684cbfacdf0820803d1e1b.
- Dashboard container successfully queried its internal API for three patients.
  Full tests include Streamlit AppTest against live APIs on both databases,
  filters, empty selections and missing/invalid/insufficient/evaluated report
  states. No fresh graphical-browser screenshot or visual accessibility audit
  was performed for this integration; earlier screenshots are retained.
- Compose FHIR Bundle import into separate reports/fhir-integration.db passed.
  Same-label repeat import inserted/updated zero rows in every table; reports
  fhir-integration-first.json and fhir-integration-repeat.json preserved.
- Actual frozen MiniLM ONNX CPU inference: evaluated all 24 holdout examples;
  data/nlp-integration-v1/report.json exactly equals the committed verified report.
  Used existing pinned cache offline, not substituted precomputed results.
- Hosted Actions: final-commit run and results are linked in the integration PR;
  workflow covers Python 3.11/3.12 PostgreSQL tests, Ruff, Compose/FHIR checks,
  one-command demo and pinned CPU NLP inference.

## Reproduction

Use the integration branch while reviewing; after merge, use main. Start Docker.
The ordinary user command is `scripts/demo.sh` (dashboard 18501, API 18000).
This review used custom ports to preserve other local demos:

```bash
COMPOSE_PROJECT_NAME=clinresearch-integration POSTGRES_PORT=25432 \
  API_PORT=28000 DASHBOARD_PORT=28501 \
  DEMO_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt scripts/demo.sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
set -a; source .env; set +a
TEST_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:25432/${POSTGRES_DB}" \
  .venv/bin/pytest -q
.venv-nlp/bin/python -m clinresearch.nlp.benchmark \
  --output data/nlp-integration-v1 --model-lock benchmarks/nlp/model-lock.json \
  --cache data/models/minilm-v1
```

CA mounting is specific to the managed certificate proxy; omit on ordinary hosts.
Choose fresh output paths on repeat runs. Install environments using README and
NLP evaluation instructions; first model download needs `--download-model`.
No application container was rebuilt and no existing data volume was removed.

## Scientific limitations

Default fixture: three fictional patients and no eligible inpatient indices.
Previously measured larger Synthea sample: 11 eligible indices, zero observed
positives. Retain insufficient_data; no research model scores or clinical validity
are established. NLP annotations are assistant-authored synthetic examples without
independent clinical review; computed benchmark metrics are not clinical accuracy.
Performance evidence is single-run, hardware-specific and not a production SLA.
This integration did not regenerate the larger performance export or its timings.

## Files changed relative to inspected main

- ` .dockerignore`
- ` .github/workflows/ci.yml`
- ` .gitignore`
- ` Dockerfile`
- ` README.md`
- ` benchmarks/nlp/assertions-v1.json`
- ` benchmarks/nlp/model-lock.json`
- ` benchmarks/nlp/verified-results-v1.json`
- ` configs/adult-return-v1.json`
- ` docker-compose.ci.yml`
- ` docker-compose.yml`
- ` docs/benchmarks/postgres-synthea20.json`
- ` docs/benchmarks/sqlite-synthea20.json`
- ` docs/dashboard.md`
- ` docs/data-dictionary.md`
- ` docs/images/portfolio-dashboard.png`
- ` docs/images/portfolio-mobile.png`
- ` docs/interview-demo.md`
- ` docs/model-card.md`
- ` docs/nlp-evaluation.md`
- ` docs/performance.md`
- ` docs/roadmap.md`
- ` docs/security-and-operations.md`
- ` docs/study-protocol.md`
- ` docs/verification.md`
- ` pyproject.toml`
- ` requirements-nlp.lock`
- ` scripts/benchmark.py`
- ` scripts/demo.sh`
- ` scripts/smoke_demo.py`
- ` scripts/smoke_explore.py`
- ` src/clinresearch/api/app.py`
- ` src/clinresearch/cli.py`
- ` src/clinresearch/configuration.py`
- ` src/clinresearch/dashboard/app.py`
- ` src/clinresearch/database/load.py`
- ` src/clinresearch/database/session.py`
- ` src/clinresearch/ingestion/fhir.py`
- ` src/clinresearch/nlp/__init__.py`
- ` src/clinresearch/nlp/benchmark.py`
- ` src/clinresearch/nlp/report.py`
- ` src/clinresearch/research/cohort.py`
- ` src/clinresearch/research/config.py`
- ` src/clinresearch/research/descriptive.py`
- ` src/clinresearch/research/evaluate.py`
- ` src/clinresearch/research/report.py`
- ` src/clinresearch/research/run.py`
- ` src/clinresearch/transformations/explore.py`
- ` src/clinresearch/transformations/summaries.py`
- ` tests/test_dashboard.py`
- ` tests/test_explore.py`
- ` tests/test_nlp_benchmark.py`
- ` tests/test_recovery.py`
- ` tests/test_research.py`
- ` tests/test_study_config.py`
