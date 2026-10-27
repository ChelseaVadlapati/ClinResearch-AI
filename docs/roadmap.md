# Evidence-based portfolio roadmap

Audit baseline: main `4e41f67` (PR #1 merged externally before this work).
Remote branches: main, feat/synthetic-ehr-mvp, feat/research-milestone-two.
PR #1's final Actions run 40439853994 passed. Local baseline on 2026-10-26
(America/New_York): Ruff check/format passed; Python 3.12, SQLite + PostgreSQL:
115 passed, 1 SQLite-only legacy constraint test skipped on PostgreSQL.
No existing features or database volumes are to be deleted. Each milestone uses
a separate draft PR; later branches may depend on earlier unmerged branches.

| Milestone | Initial evidence/status | Exact targets and acceptance |
| --- | --- | --- |
| 1 Interoperability | Absent: only `ingestion/csv.py`, CLI `ingest`; no migrations | Add `ingestion/fhir.py`, medication/provenance tables in `database/models.py`, Alembic revisions, `ingest-fhir`, `tests/test_fhir.py`, `docs/fhir-mapping.md`. Synthetic Bundle/resource imports reconcile accepted/rejected/skipped resources, resolve local references, repeat idempotently, and drive existing APIs without CSV regression. |
| 2 Research | Partial: `research/cohort.py`, `evaluate.py`, `report.py`, `run.py`; tested eligibility, flow, purging, fixed logistic baseline; insufficient observed positives | Add versioned `research/config.py`, config file, descriptive summaries and `docs/data-dictionary.md`, methodology/model card. Configuration validated and fingerprinted; default behavior preserved; train-only features, outcome accounting and insufficient-data regressions pass. Additional model only if independent data meet justified sufficiency criteria. |
| 3 NLP | Partial: deterministic `research/notes.py` with assertion labels and spans; no independent benchmark/transformer | Preserve rules; add separate `nlp/` experimental CPU workflow, curated independent synthetic evaluation fixture, optional locked dependencies, script, `docs/nlp-evaluation.md`. Track source/license/model revision, evaluate only supported labels; no invented benchmark, no readmission feature reuse. Report unavailable-model or annotation blockers honestly. |
| 4 Dashboard | Partial: aggregate API, all-patient charts, quality and saved research flow; no filters/downloads/distributions | Extend `transformations/summaries.py`, `api/app.py`, `api/schemas.py`, `dashboard/app.py`, tests. Backend cohort filters consistently scope aggregates; downloadable aggregate CSV/report; validated source/study/software provenance; data-driven empty/error/sufficiency states. |
| 5 Reproducibility/portfolio | Partial: hash lock, Docker, CI, screenshots/protocol, tests; no benchmarks/demo wrapper/config validation | Reuse migrations from M1. Add config/logging, `scripts/demo.sh`, benchmark harness and recorded conditions, `docs/interview-demo.md`, capabilities and evidence. Test recovery/privacy boundaries; no HIPAA claim; publish exact commands and measured performance only. |

## Dependencies and risks

M1 precedes M2; M3 stays separate from predictive features; M4 consumes validated
M2/M3 artifacts; M5 verifies the integrated stack. Migrations are brought forward
to M1 to avoid silently modifying an existing schema. Existing legacy tables may
lack constraints: migration adoption must inspect rather than erase their data.
FHIR support is an explicit supported R4 subset, not a full conformance validator.
Unknown resource types, ambiguous references and unsupported value shapes must
be audited rather than silently mapped. Namespace provenance prevents unrelated
exports with reused IDs being accidentally joined.

Synthetic return outcomes are sparse: the available two-patient generated export
has one index and zero positives. The historical 234-patient export is absent.
Neither permits useful model comparison; do not manufacture positives. Annotation
independence and transformer model licensing/download availability must be checked
before claims. Rule/template consistency is not clinical NLP validation.
Public APIs must stay aggregate-only. Public demo provenance is synthetic; import
format alone cannot verify provenance. No production authentication/HIPAA claims.

## Validation gate for each milestone

Record Ruff, format, pytest SQLite/PostgreSQL counts, relevant Compose/API/dashboard
smoke results and hosted Actions URL in `docs/verification.md` before starting the
next milestone. Review changes and preserve fixtures, reports and volumes. A failed
or blocked check stays explicitly failed/blocked, not claimed as passing. PR bodies
summarize exact reproduction commands and unresolved technical/research limits.
