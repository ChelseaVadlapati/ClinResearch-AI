# Milestone 2: simulated notes and readmission research

This workflow is an executable research demonstration using synthetic records.
It does not predict risk for real patients. The clinical data platform remains
Milestone 1: validated Synthea CSV ingestion, normalized SQL tables, import audit,
aggregate API, dashboard, and automated tests. A third milestone has not been
specified.

## Run with Docker Compose

Rebuild after pulling the Milestone 2 changes, then start the existing demo:

```bash
docker compose up --build -d --wait
# Use the fixture solely to check the pipeline and its insufficient-data behavior.
docker compose run --rm ingest clinresearch analyze \
  --observation-end 2025-01-01 --split-date 2024-01-01 \
  --output /app/reports/research
```

The command does not retrain on each dashboard visit. Open dashboard port 8501
and click **Refresh data** to see the saved report. The API serves aggregates at
`GET /research/report`. Before a run it returns `status: not_run`; malformed reports
return HTTP 503. The API mounts `reports/` read-only. Set `RESEARCH_REPORT_PATH`
for a different report location (or use a separate Compose override).

Each run writes a **new** directory and refuses to overwrite one:

- `cohort.csv`: one eligible index discharge per patient, features, and outcome.
- `simulated_notes.jsonl`: conspicuously labeled text, source IDs, discharge time,
  template version, and extracted mentions with offsets and assertion labels.
- `report.json`: cohort audit, concept counts, temporal split counts, limitations,
  dataset fingerprint, and evaluation when sufficient data exist.

The first two files stay local and are not API endpoints. Artifacts are ignored
by Git. Use a new output folder for later runs; the dashboard's default remains
`reports/research/report.json`. To replace that displayed snapshot, archive the
old folder first, then run again into a new `reports/research` directory.

For local Python development, install the updated `requirements.lock` and project
as documented in the README, activate the environment, and load `.env`. Then:

```bash
clinresearch analyze --observation-end 2025-01-01 --split-date 2010-01-01 \
  --output reports/research
```

Use an independently chosen split date appropriate to your study. Do not select
the date by comparing test scores. The observation boundary must come from export
provenance; never infer complete follow-up from the last observed encounter.
Do not import new data while generating a report. A saved report is a historical
snapshot, not automatically recomputed after later imports.

## Cohort and outcome contract

- Include `inpatient` encounters only, with start before the exclusive observation
  boundary (00:00 UTC on `--observation-end`).
- Merge overlapping or touching inpatient encounters into one episode, including
  transfers. An episode with an unknown stop cannot serve as an index. Its start
  can still establish a return after a previous discharge.
- Select each patient's first eligible discharge at age 18 or older. Exclude
  missing discharge, death on/before the end of the 30-day horizon, and discharge
  whose 30-day horizon reaches or exceeds the observation boundary.
- Positive outcome: another inpatient episode starts **after discharge and at or
  before discharge + 30 days**. Same-time continuation is merged; outpatient visits
  do not count. This is an **observed all-cause inpatient return**, not a verified
  unplanned readmission, CMS metric, or validated clinical endpoint.
- Negative outcome: no such return within the fully observed assumed horizon.
  Death exclusions apply to both positive and negative candidates. The audit
  counts candidates considered until the first eligible index, not every excluded
  encounter in the entire export.

Full export coverage is assumed, not proven. Synthea does not establish continuous
real-world enrollment, out-of-system care capture, or real-world label accuracy.
Excluding death instead of modeling competing risks also changes the population.

## Feature availability and splitting

The fixed numeric features are age at discharge, merged length of stay in days,
prior inpatient episode starts in the 365 days before discharge, and distinct
previously documented condition codes. Conditions must start **before the calendar
date of discharge**, conservatively excluding same-day onset because CSVs do not
supply a recording time. Resolved conditions remain historical conditions.
Retrospective onset coding is still a limitation: onset is not availability time.

No identifiers, future encounters, outcomes, future notes, or post-discharge
observations are model features. Race, gender, and ethnicity are not baseline
features; this does not establish fairness.

Training indices have a complete label horizon strictly before `--split-date`.
Test indices discharge on/after that date. The intervening 30-day boundary region
is purged. One index per patient makes patient sets disjoint. `StandardScaler`
and fixed logistic regression (`C=1`, seed 42, maximum 2000 iterations) fit only
training rows. The decision threshold is fixed at 0.5. There is no holdout-based
feature selection, threshold selection, tuning, or recalibration.

Training requires at least 10 patients and 2 members of each outcome class in
**each** partition. These guardrails only prevent degenerate evaluation; they are
not a sample-size or statistical-power justification. Otherwise the report says
`insufficient_data` and contains no fitted model or performance scores. The tiny
committed fixture is expected to take this path.

Reports include ROC AUC, average precision, Brier score, sensitivity/specificity,
confusion counts, test prevalence, and five equal-width calibration bins. A
constant predictor using **training** prevalence supplies a comparator. Seeded
500-replicate held-out-patient bootstrap intervals cover AUC, AP, and Brier score;
single-class replicates are omitted and the retained count is reported. Intervals
condition on the fitted model, exclude training uncertainty, and say nothing
about transportability to real patients. Model means, scales, coefficients, and
intercept are saved as JSON; there is no unsafe pickle loading or clinical
prediction endpoint.

## Simulated notes and concept extraction

Notes are deterministic templates made from eligible discharge-time features.
Every note begins `SIMULATED NOTE`, with explicit synthetic provenance. The
outcome and future records are never embedded. Only vocabulary-matched historical
conditions are mentioned; an absent mention does not exclude a condition.

The rule-based extractor recognizes six concept families: hypertension, diabetes,
heart failure, COPD, asthma, and chronic kidney disease. It returns source spans
and `present`, `negated`, `uncertain`, or `family` assertions. Cues scope an entire
sentence, with family, negation, then uncertainty taking precedence. This simple
scope is deliberately conservative and can misclassify mixed statements. It does
not handle general clinical language, abbreviations beyond the small dictionary,
complex temporality, or all clinical concepts.

NLP output is separate from the structured baseline. Adding text features derived
from the same structured records would not demonstrate independent information.
Template round-trip checks and curated assertion tests are software verification,
not an independently annotated NLP benchmark. Do not report clinical extraction
accuracy from these tests.

## Validation and limits

Tests exercise 30-day boundaries, transfers, missing stops, minors, death and
follow-up exclusions, patient uniqueness, future-record invariance, assertion
spans, temporal purging, training-only scaling, deterministic evaluation,
insufficient-data behavior, report artifacts, API handling, and dashboard states.
Run `pytest -q`; set `TEST_DATABASE_URL` to include isolated PostgreSQL schemas.

Synthea generation and larger cohort imports follow the existing README. Use a
separate database for research to avoid mixing the tiny fixture with generated
records. A larger population may still lack sufficient eligible positives in a
partition. Never invent outcomes or present deliberately constructed software
fixtures as a valid research cohort. No external validation, prospective study,
clinical utility, causal conclusion, or real-world performance is claimed.
