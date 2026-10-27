# Synthetic inpatient-return baseline model card

## Intended use and status

Research software demonstration only. Not clinically validated and not suitable
for diagnosis, treatment, triage or real patient predictions. The available
observed synthetic cohorts are insufficient; no validated model or performance
claim is published. A second model is deliberately not compared without sufficient
independent outcomes. Artificially balanced software fixtures test execution only.

## Design

One earliest eligible adult discharge per patient, observed all-cause inpatient
return within 30 days, and an export-provenance-supplied observation boundary.
Overlapping/touching stays merge; death by the horizon and incomplete follow-up
exclude indices. `study-protocol.md` defines the endpoint; `data-dictionary.md`
defines feature availability. A date window filters index candidates only, not
prior history or future outcome ascertainment. Configurable age bounds remain adult.

A fixed StandardScaler + LogisticRegression(C=1, max_iter=2000, random_state=42)
fits training data only. Train label horizons must end strictly before the split;
test discharges start on/after it. Boundary indices are purged, and patients are
disjoint. No holdout tuning, threshold optimization or synthetic oversampling.
Threshold 0.5 and 500 fixed-seed held-out-patient bootstrap draws are unchanged.

Version-1 study configuration forbids silently changing the 30-day endpoint,
365-day lookback or seed. Unknown config fields and contradictory dates/ages
fail validation. Configuration and cohort hashes, exact config JSON, sklearn
version and, when permitted, fitted coefficients are saved with each new run.
The example `configs/adult-return-v1.json` requires >=100 patients and >=20 of each
class in EACH partition. Historical no-config behavior preserves >=10/>=2 software
guardrails; configuration can tighten but cannot lower them. Neither threshold
constitutes a sample-size/power justification. Formal study design is still needed.

## Evaluation and limitations

Only sufficiently populated partitions produce AUROC, average precision, Brier,
calibration bins, sensitivity/specificity, confusion counts and bootstrap intervals.
Otherwise `insufficient_data` omits both model and scores. A constant prediction
using training prevalence provides a comparator. Class counts and descriptive
summaries do not imply a model was fit. Bootstrap omits single-class resamples,
conditions on the fitted model and excludes training uncertainty.

Synthetic distributions, unknown outside care, onset-versus-entry timestamps,
missing history, death exclusion and selection of one index limit interpretation.
Race/gender exclusion from predictors does not establish fairness. No external,
prospective or subgroup clinical validation. NLP templates are not independent
features. Outcome scarcity prevents meaningful model comparison at present.
