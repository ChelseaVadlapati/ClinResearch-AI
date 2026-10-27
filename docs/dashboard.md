# Dashboard interpretation and reproducible downloads

`GET /cohort/explore` accepts `as_of`, inclusive `minimum_age`/`maximum_age`, exact
`gender`, exact `encounter_class`, inclusive `encounter_start` and exclusive
`encounter_end`. Invalid age/date bounds return 422. Age uses completed years at
reference date or death if earlier. An encounter criterion selects patients with
at least one matching visit; all charts then include their full recorded history.
This is exploratory selection, not the saved model's index cohort definition.
Queries use bound SQL parameters and PostgreSQL repeatable-read snapshots.

The response contains selected counts/demographics/ages, monthly visits, condition
aggregates, missingness, selected filters, package version and latest import metadata.
The import audit is explicitly database-wide. Latest-batch version is not a claim
that all stored records came from that batch: upserts retain earlier records.
No source filenames, raw FHIR identifiers, patient IDs or note text are returned.

`download=true` returns a CSV of aggregate table counts and monthly counts. The
UI also downloads aggregate count CSV, filtered JSON summary and saved study JSON.
They contain exact filter/configuration values needed for reproduction against
the same data snapshot. No patient-level export is available from public routes.
These synthetic-only small aggregates are not a deidentification mechanism for
real data; do not connect a public demo to real records.

Saved study reports show configuration hash, cohort flow and observed class counts.
Feature histograms and descriptive intervals appear only when present; calibrated
predictions appear only in an evaluated report. `insufficient_data` remains explicit.
Dashboard filters never alter these saved artifacts or trigger model fitting.

`GET /nlp/report` reads `NLP_REPORT_PATH` (default `reports/nlp/report.json`). It
validates label order, finite metrics, holdout counts and execution status, returning
only aggregate results. Error examples, local model paths and source text remain
local. Missing files return not_run; malformed data return sanitized HTTP 503.
The UI prominently distinguishes synthetic software benchmark results from clinical
accuracy. Dataset splits differ from the patient cohort and are never mixed.

Every control has a visible label. Charts have table alternatives, meaningful
headings and empty/error messages; layouts use Streamlit's responsive components.
Desktop and 390-pixel viewport checks are recorded in verification evidence.
No authentication is added for this loopback-only synthetic demo; public production
hosting is outside the current threat model and is not HIPAA certified.
