# Add simulated-note NLP and leakage-controlled readmission research

The clinical data platform now supports an offline `clinresearch analyze`
workflow that derives an explicit adult inpatient cohort, generates labeled
simulated discharge notes, extracts a bounded clinical vocabulary with assertion
labels, and evaluates a fixed logistic baseline using disjoint patients and a
purged temporal split. Preprocessing fits training data only. Reports include
cohort exclusions, a constant baseline, discrimination/calibration metrics,
bootstrap intervals, reproducibility metadata, and synthetic-data limitations.
Insufficient data produce an explicit no-model result.

Adds a read-only aggregate report API and dashboard section, a hash-locked
scikit-learn dependency, CLI/SQL/NLP/model/UI tests, and reproducible commands.
No patient-level prediction endpoint or claim of clinical validation is added.
Milestone 1 remains intact; a third milestone is not yet specified.

Validation: 69 tests passed on each of Python 3.11 and 3.12 with SQLite and
PostgreSQL; lint/format checks; Docker build/startup; live API/dashboard smoke
checks. A 234-patient official Synthea export produced 122 eligible discharges
and simulated notes but only one return outcome, correctly withholding model
scores. Fitting and metric paths passed controlled software-fixture tests; this
is not sufficient-data research validation. See docs/verification.md and
docs/research.md for definitions, commands, and evidence.
