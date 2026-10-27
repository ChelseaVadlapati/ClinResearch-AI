# Study protocol 1.1

## Objective and source population

Verify an end-to-end research software workflow for a fixed logistic baseline of
30-day inpatient return using synthetic Synthea CSV exports. This is not a study
of clinical efficacy. The public demo uses only the three fictional patients in
`tests/fixtures/synthea`; generated Synthea exports must use a separate database.
No real EHR data, patient notes, or clinically validated models are supplied.

## Inclusion, exclusions, and index encounter

Use inpatient records starting before the provenance-supplied exclusive UTC
observation boundary. Merge overlapping or touching stays into episodes. Select
one earliest eligible discharge per patient, aged at least 18 at discharge.
Exclude missing discharge, age under 18, a 30-day horizon reaching or exceeding
the observation boundary, and death on or before that horizon. These criteria
apply regardless of outcome. Unknown-stop episodes cannot be index encounters.
Negative durations fail ingestion and database constraints; legacy negative
inpatient durations abort analysis rather than being clipped or used as features.

`cohort_flow.csv` and `report.json` report mutually exclusive dispositions within
record, episode, and patient units. Sum within a unit only. Merged records explain
the difference between inpatient records and episodes. Episodes after a selected
index are counted as not selected, rather than tested again for eligibility.
The flow describes accepted database rows; import JSON separately accounts for
source validation rejections. Records absent from later imports are not deleted.

## Outcome definition

A positive outcome is an observed inpatient episode start strictly after index
discharge and at or before discharge plus 30 days. No such start is a negative
under the assumed complete export coverage. Transfers are merged; outpatient
visits do not qualify. The endpoint is all-cause observed inpatient return, not
verified unplanned readmission. No outcomes are generated to balance classes.

## Feature availability

| Feature | Availability at index discharge |
| --- | --- |
| Age | Completed years from date of birth |
| Length of stay | Merged episode stop minus start, in days |
| Prior inpatient count | Earlier episode starts within 365 days before discharge |
| Known conditions | Distinct system/code pairs with onset before discharge date |

Linked conditions also require their encounter to belong to the same patient and
to have started and ended by index discharge. Same-day onset and unresolved
linked encounters are excluded conservatively. Resolved conditions remain history.
Onset dates are not recording timestamps: retrospective availability remains
uncertain. Simulated notes use these features only, carry an explicit simulated
label, and are not independent evidence or model inputs. Identifiers, outcomes,
future visits, and post-discharge observations are never features.

## Time split and reproducibility

Prespecify the split date without consulting performance. Training horizons must
end strictly before it; test discharges occur on or after it. Purge the intervening
boundary region. One index per patient prevents patient overlap. Fit scaling and
fixed logistic regression on training data only; use threshold 0.5, seed 42 and
500 held-out-patient bootstrap draws. Dependencies are hash locked; reports retain
the cohort SHA-256, split, coefficients when fitted, and software version.
Use the pinned Synthea generator, dates, seeds and runtime documented in README.

Both train and test require at least 10 patients and at least two of each outcome
class. These are software guardrails, not statistical power calculations. If
unsatisfied, retain `insufficient_data` with no model or scores. The previously
reported 234-patient export had only one eligible positive; it cannot support
model evaluation. Controlled evaluation test fixtures are software tests only.

## Limitations

Synthetic data cannot establish clinical validity, representativeness, fairness,
or transportability. Export coverage, outside care and recording time are not
verified. Excluding death changes the target population and does not model
competing risks. One eligible discharge per patient changes the estimand. The
small rule-based NLP vocabulary is not validated against independent clinical
annotations. Bootstrap intervals condition on the fitted model and omit training
uncertainty. No external validation, clinical deployment or research performance
claim is justified. See `docs/verification.md` for observed checks and limitations.
