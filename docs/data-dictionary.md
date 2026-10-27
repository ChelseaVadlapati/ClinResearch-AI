# Research data dictionary

All counts describe loaded synthetic records. They are not population estimates.
The relational schema is defined in `src/clinresearch/database/models.py`; FHIR
source mappings and differences are in `fhir-mapping.md`.

| Research field | Type/unit | Definition and availability | Missingness |
| --- | --- | --- | --- |
| patient_id, encounter_id | Local string IDs | Traceability in local cohort CSV only; never predictors or public row endpoints | Required |
| discharge | Zoned UTC timestamp | End of merged index inpatient episode | Missing stop excludes index |
| readmission_30d | Binary observed label | Later inpatient start in (discharge, discharge + 30 days] | Assumes complete observation through horizon; incomplete follow-up excluded |
| age | Completed years | Calculated at discharge from birth date | Birth date required at ingestion; configurable adult bounds |
| length_of_stay_days | Nonnegative floating days | Merged stop minus start / 86400 | Negative durations rejected; no clipping/imputation |
| prior_inpatient_365d | Integer episodes | Earlier starts within 365 days before index discharge | Zero means no qualifying recorded history, not guaranteed absence of care |
| known_condition_count | Integer distinct system/code pairs | Onset before discharge date; linked encounter ended by discharge | Zero means none recorded under availability rules, not no disease |
| known_conditions | Local text descriptions | Used only to construct explicitly simulated notes | Not an independent text modality or predictor |

MedicationRequest records are orders; neither exposure nor adherence is inferred.
FHIR identifier and coding provenance stays in local `fhir_resources`; raw
rejections stay in local audit tables/files. Public endpoints expose aggregates.

`descriptive.features` reports observed/missing counts, min/Q1/median/Q3/max and
five-bin aggregate histograms. Cohort model features currently require complete,
finite nonnegative values; summaries still account explicitly for missing values.
Histograms count each observed value exactly once; the final bin includes its
upper boundary. Counts and outcome fractions remain available on small datasets.
Wilson 95% intervals are displayed only for at least 20 independent index patients
and at least two outcomes in each class; otherwise an explicit reason is stored.
These intervals describe synthetic-sample binomial variation only, not clinical
uncertainty or representativeness. No hypothesis testing or causal inference.
