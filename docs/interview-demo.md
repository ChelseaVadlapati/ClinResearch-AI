# Five-minute research software demonstration

Preparation: run `scripts/demo.sh`, open the printed dashboard URL, and keep the
README, study protocol and the latest PR checks available. Use only the fictional
fixture. This is an independent portfolio project, not a University of Florida
product or evidence of clinical deployment.

## 0:00–0:40 — Research question and boundaries

“I built this to demonstrate a reproducible biomedical research workflow: integrate
synthetic health records, define an auditable cohort, and test an observed 30-day
inpatient-return baseline. It is synthetic-only and not clinically validated.”

Show the architecture diagram and explain the separation between normalized source
data, exploratory aggregates, saved research analysis and the separate NLP experiment.

## 0:40–1:35 — ETL and interoperability

Show the CSV/FHIR mapping and an import audit. Explain Patient/Encounter/Condition/
Observation/MedicationRequest support, local reference validation, provenance hashes,
idempotent imports and additive migrations. Point out the documented FHIR subset:
component observations are rejected rather than silently flattened. Show that
negative durations and invalid links are tested and transaction failures roll back.

## 1:35–2:25 — Research data engineering and statistical design

Open the saved study configuration and cohort flow. Explain one eligible adult
index per patient, transfer merging, complete assumed follow-up, death exclusions,
feature availability and the purged patient-disjoint time split. Scaling fits only
training data. The fixture has no eligible indices, so `insufficient_data` is the
correct result. The generated performance sample also lacks observed positives.
No synthetic outcomes were invented to make fitting succeed.

## 2:25–3:15 — Research visualization and reporting

Enable cohort filters and select recorded gender F: the fictional demo selects one
patient. Select inpatient encounters: it shows an informative empty selection.
Explain that filters select patients and summarize their full history; saved model
reports do not change with filters. Download aggregate CSV/JSON and point to the
filter/configuration values needed to reproduce them. Show the latest import time
and explain why latest-batch provenance is not full-database provenance.

## 3:15–4:10 — NLP experiment and error analysis

Show `docs/nlp-evaluation.md` and its computed artifact. Explain the preserved rule
baseline, train-only TF-IDF and frozen CPU MiniLM with pinned model hashes. The
fixed synthetic holdout has only 24 examples and no independent clinical annotation
review. TF-IDF had higher macro F1 than MiniLM here; do not sell a transformer win.
Show a real error such as negation scope across clauses. No text-model outputs are
used as independent readmission predictors.

## 4:10–5:00 — Reproducibility, quality and limitations

Show successful hosted CI for the reviewed revision: lint, Python 3.11/3.12 with
PostgreSQL, Compose/API/dashboard checks and CPU NLP inference. Open the measured
performance report and name its dataset, hardware and single-run limitations.
Explain the tradeoff: full-export validation is transparent but memory-bound;
streaming ingestion, richer FHIR profiles and independently reviewed data are
future work. End with the evidence: reproducible software and honest uncertainty,
not unvalidated clinical conclusions.

## Resume-ready description

Built a reproducible synthetic-EHR research platform with CSV/FHIR R4 ingestion,
PostgreSQL and Alembic, aggregate FastAPI/Streamlit reporting, versioned research
cohorts, leakage-controlled logistic modeling, and a separate CPU transformer NLP
experiment; verified data integrity and recovery with automated tests, Docker
Compose smoke checks, and GitHub Actions.

Use this wording only for the implemented portfolio project. Do not add clinical
accuracy, production deployment, employer affiliation or patient-impact claims.
