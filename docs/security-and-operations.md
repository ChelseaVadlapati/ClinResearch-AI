# Configuration, privacy and recovery boundaries

## Actual deployment scope

The supplied demo runs synthetic data on loopback-only PostgreSQL/API/Streamlit
ports. There is no external clinical service, real EHR connection, authentication,
PHI pipeline or HIPAA compliance claim. Public hosting with real or sensitive
records is outside this design; authentication, authorization, audit retention,
network controls and reidentification risks would require a new threat assessment.
Aggregate outputs alone are not a deidentification guarantee.

Public routes never return patient rows, FHIR source filenames/identifiers or NLP
error-example text. Raw synthetic rejections, local cohort CSVs, simulated notes
and detailed benchmark errors stay in ignored local files/database tables. Test
fixtures and committed benchmark examples are explicitly fictional. Model weights
are not committed; public Apache-2.0-declared model assets are pinned by revision/hash.

## Secrets and configuration

`DATABASE_URL` is required and restricted to SQLite or PostgreSQL+psycopg. Invalid
configuration exits with a sanitized message; credentials are not echoed. The
setup script generates a random local password into ignored mode-0600 `.env` and
refuses overwrite. Never commit secrets or include them in screenshots. Both Git
and Docker exclusions cover `.env`, generated data, reports and virtual environments.
Package locks are hash-checked; TLS verification stays enabled. Corporate proxy CAs
are mounted read-only for dependency installation, never copied into source.

Application CLI logs are JSON objects with UTC timestamp, level, logger and event.
They do not serialize exception tracebacks, database URLs or input records. FHIR
date/timestamp validation uses fixed messages rather than echoing malformed values.
Normal service logs remain framework-managed; use the local audit report for
record-level rejection investigation, not application logs.

## Migration and partial-failure semantics

`clinresearch init-db` and ingestion apply additive Alembic revisions. Existing
records and volumes are preserved; incompatible existing column layouts require
manual review. Legacy missing constraints are not silently repaired. Back up a
valuable database before migration. Destructive downgrade is intentionally disabled.

Ingestion validates the entire input, writes `validated_not_committed` evidence,
then atomically commits accepted records and import audit. Unsupported/invalid
records are recorded; exit 2 means accepted rows committed with rejections. Database
or integrity failure rolls back and exits 1. Reimports cannot reassign existing
events to other patients or update demographics so retained events lie outside the
patient lifetime. Tests verify rollback followed by successful idempotent recovery.

If the final filesystem report write fails after database commit, CLI says
`Import committed; final report write failed` and points to `import_runs`; it does
not falsely claim rollback. Database audit is authoritative. Report path failures
before loading leave the database untouched. Research and NLP runs refuse existing
output directories; report.json is published only after research artifacts are
written. Incomplete output directories remain for diagnosis; choose a fresh path.

## Demo operations

`scripts/demo.sh` creates/reuses its own Compose project and keeps all volumes.
It defaults to PostgreSQL 15432, API 18000 and dashboard 18501 to avoid the standard
manual demo ports. Each run gets fresh import/research/NLP report paths. It uses
source-mounted services without an application-image rebuild. The lightweight demo
runs rules/TF-IDF only; transformer status is honestly not_run until explicitly run.

Set COMPOSE_PROJECT_NAME, POSTGRES_PORT, API_PORT or DASHBOARD_PORT to use other
available ports. Set DEMO_CA_BUNDLE to a trusted combined CA bundle when needed.
To stop your demo, use `docker compose -p clinresearch-portfolio -f docker-compose.yml
-f docker-compose.ci.yml stop`; no volume deletion is required. Keep the printed
artifact path to reopen a particular run using API report-path environment variables.
