# Synthetic FHIR R4 mapping

This adapter supports an explicit R4 subset, not arbitrary FHIR profiles or a
FHIR server. It performs no reference URL fetching. Only synthetic exports are
permitted; `--synthetic-only` is an operator assertion, not a detector of real PHI.

```bash
# Use a separate database; do not combine equivalent CSV/FHIR populations.
export DATABASE_URL=sqlite:///fhir-demo.db
clinresearch ingest-fhir tests/fixtures/fhir/bundle.json --dataset fictional-v1 \
  --synthetic-only --report reports/fhir-demo.json
# Repeat with the SAME dataset version to verify zero inserts/updates.
# Existing aggregate API/dashboard commands then work against this DATABASE_URL.
```

Input may be one resource, a collection/transaction/batch/document Bundle, or a
directory of JSON files. Complete import-local references use `Type/id` or exact
Bundle `fullUrl` (including `urn:uuid`). Historical versions, contained references,
remote-only references, history and response bundles are unsupported. No operations
in a transaction bundle are executed: resources are read as an offline snapshot.
Do not submit delete/history semantics. Unsupported resource types are counted
separately in `source.unsupported_resource_counts`; supported invalid resources
are rejected with reasons. CLI exits 2 after loading accepted rows if any supported
records were rejected, 1 for structural errors, and 0 for a clean supported import.

| Relational field / CSV | Supported FHIR source | Semantic boundary |
| --- | --- | --- |
| Patient ID / Id | Patient.id, dataset namespace | UUID5 of dataset/type/id; IDs preserved locally in fhir_resources |
| Birth/death | birthDate / deceasedDateTime | Full dates required; unknown death date rejects deceasedBoolean=true |
| Gender | gender | female/male map to F/M; unknown preserved |
| Race/ethnicity | Not mapped from extensions yet | Explicit unknown; do not imply CSV equivalence |
| Encounter START/STOP | period.start/end | Zoned timestamps; nonnegative duration; finished requires end |
| Encounter class | class.system + code | R4 ActCode IMP/AMB/EMER/OBSENC/VR/HH; AMB does not distinguish CSV wellness |
| Encounter code | type[0].coding | Deterministic system/code selection; all coding retained in local provenance |
| Condition START/STOP | onsetDateTime/abatementDateTime | Date-level schema; onset is not recording time |
| Condition CODE/SYSTEM | code.coding | URI coding system retained, e.g. http://snomed.info/sct differs from CSV SNOMED-CT |
| Observation DATE | effectiveDateTime | Zoned timestamp required |
| Observation VALUE | valueQuantity/String/Boolean/CodeableConcept | Exact finite quantities only; bounded, component-only, absent and other shapes rejected |
| Observation UNITS | valueQuantity.code or unit | No conversion; do not combine unlike units |
| Medication order | medicationCodeableConcept, authoredOn, status, intent | New table; order does not establish administration/adherence; medicationReference unsupported |
| Parent links | subject and optional encounter | Must resolve to accepted records and same patient; lifetime validated |

Full R4 allows fields and variants beyond this subset. The adapter rejects these
explicitly rather than guessing. Multiple codings choose lexicographic system/code
for the single normalized concept; all codings and identifier system/value pairs
remain in `fhir_resources`. Resources and full source files are fingerprinted.
Local audit rejections preserve raw synthetic resources. Neither raw resources nor
patient-level identifiers are added to public endpoints.

Repeated imports use the same version namespace and source logical IDs; missing
records are never deleted. Exact duplicates are audited; conflicting copies and
ambiguous fullUrls are all rejected independent of ordering. Children of rejected
parents are rejected. Accepted rows and import audit commit atomically. Do not
reuse a dataset version for an unrelated population. Changed source files update
stable resource IDs with an audited import and source hashes.

## Equivalence and provenance

`tests/fixtures/fhir/bundle.json` is hand-authored fictional test data corresponding
to the existing CSV fixture, with one extra fictional medication order. Tests
compare birth/death/gender, encounter times/codes, condition dates/codes, and
observation times/codes/numeric values/units. No equivalence is claimed for source
IDs, race/ethnicity extensions, wellness classification, or coding-system labels.
This fixture is not presented as an official Synthea run.

Generate genuine paired exports using the existing pinned JAR and seeds:

```bash
scripts/generate_synthea.sh "$PWD/data/fhir-paired" 2 both
clinresearch ingest-fhir data/fhir-paired/fhir --dataset synthea-3.3.0-seed42-p2 \
  --synthetic-only --report reports/fhir-paired.json
```

## Additive migrations

`clinresearch init-db` and import commands run Alembic through the configured
SQLAlchemy connection. Revision `0001_existing` adopts compatible existing tables
without deleting rows; `0002_fhir` adds medication/provenance tables. Schema
mismatches fail for manual review. These migrations do not repair corrupt legacy
rows or assert missing legacy constraints. Take a backup before migrating a
valuable database. Downgrades that could delete work are deliberately unsupported.

Actual fixed-seed paired-export verification accepted all 2 Patient, 545 Encounter,
294 Condition and 419 MedicationRequest resources. It accepted 5,031 of 5,276
Observation resources and explicitly rejected 245 component-only/absent-value
shapes. CSV exported 7,793 observations with different flattening semantics. See
`docs/verification.md`; these are software accounting checks, not research findings.
