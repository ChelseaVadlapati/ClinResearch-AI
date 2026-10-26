# CSV validation and rejection contract

CSV inputs are UTF-8 (optional BOM), comma-delimited, with exact case-sensitive
headers. Additional Synthea columns are permitted and ignored for accepted rows.
Strings are preserved as strings (including codes with leading zeroes); whitespace
is stripped. Blank optional values are not silently interpreted as zero.

| File | Required headers |
| --- | --- |
| patients.csv | Id, BIRTHDATE, DEATHDATE, GENDER, RACE, ETHNICITY |
| encounters.csv | Id, START, STOP, PATIENT, ENCOUNTERCLASS, CODE, DESCRIPTION |
| conditions.csv | START, STOP, PATIENT, ENCOUNTER, CODE, DESCRIPTION |
| observations.csv | DATE, PATIENT, ENCOUNTER, CODE, DESCRIPTION, VALUE, UNITS, TYPE |

`conditions.SYSTEM` and `observations.CATEGORY` are optional. A blank/missing
condition system defaults to Synthea's SNOMED-CT; observation category defaults to
`unknown`. Observation codes retain Synthea's LOINC coding convention.

## Whole-import failures (exit 1)

Missing files/headers, duplicate headers, undecodable text, and malformed CSV
quoting prevent the entire import before any database writes. Operational or
transaction failures also fail without committing partial table updates. A JSON
report marked `validated` is not evidence of a committed transaction.

## Row rejections (accepted rows load; CLI exits 2)

- Incorrect field count; missing/invalid UUID patient or encounter IDs.
- Missing required birth/start/date, code, observation value, or observation type.
- Invalid ISO dates. Birth/death and condition dates use `YYYY-MM-DD`.
  Encounter/observation timestamps accept ISO datetime or date-only midnight.
  Offset-aware timestamps normalize to UTC; naive timestamps assume UTC.
- Death before birth, stop before start, or an event before the patient's birth.
- Non-finite or nonnumeric `VALUE` when `TYPE=numeric`.
- Patient references absent from accepted patients in this export.
- Nonblank encounter references absent from accepted encounters, or referencing
  an encounter belonging to a different patient. Rejected parents cause dependent
  child rejections. A blank encounter reference is permitted for observations
  and conditions; their patient reference is always required.
- Exact duplicates after normalization: accept one, report the others.
- Conflicting normalized records sharing a stable key: reject **all** conflicts,
  so acceptance does not depend on file order.

Stable keys: patient/encounter source UUIDs; condition SHA-256 of patient,
encounter, start date, system, code; observation SHA-256 of patient, encounter,
UTC time, code, category, value, units, type. The hashes identify synthetic
records; they are not an anonymization mechanism.

Optional death/stop/encounter/units become SQL NULL. Blank demographic fields,
encounter class, and descriptions become `unknown`. Text and other nonnumeric
observation types remain strings without a numeric projection. No imputation,
unit conversion, diagnosis inference, or clinical range filtering is performed.

Every rejected record has a table name, logical CSV record number (header = 1),
reason, and original source fields in the JSON report and `rejected_rows` table.
Logs report table/record/reason without field values. These reports may include
all source columns: the project must receive **only synthetic data**. Structural
failures are emitted to stderr and do not create a successful import audit.

Reimports keep clinical-style row counts stable but append an import audit.
Review exit 2 and rejection reasons before using summaries; never equate
successful partial loading with a clean source dataset.
