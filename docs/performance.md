# Measured synthetic-data performance

Measurements taken on 2026-10-27 with Python 3.12.14, Linux x86_64, an AMD EPYC
9V74 host, 3 available logical CPUs and an 8 GiB container memory limit. PostgreSQL
16.15 ran in the managed Docker daemon; SQLite version is recorded in the JSON.
These are sequential single-run measurements after generation/testing finished,
with potentially warm filesystem caches. They are not production SLAs, concurrency
benchmarks, statistical comparisons or evidence of asymptotic scalability.

Input: official Synthea v3.3.0, requested population 20, seed/clinician seed 42,
reference 2024-01-01, end 2025-01-01, Florida, Java 21 and one generator thread.
Export: 23 patients (20 alive/3 deceased overflow), 4,177 encounters, 2,617 conditions,
66,978 observations. Accepted: 23/4,175/2,617/66,958 respectively. Inspect validation
reasons before interpretation; no rejected rows are silently repaired.
Rejections were seven events after recorded death (two encounters, five observations)
and fifteen duplicate observations. Full source SHA-256 values, database/hardware details and exact timings are saved
in `docs/benchmarks/postgres-synthea20.json` and `sqlite-synthea20.json`.

| Operation | PostgreSQL seconds | SQLite seconds |
| --- | ---: | ---: |
| Validation | 1.535 | 1.906 |
| Migration | 0.092 | 0.010 |
| Initial load | 9.080 | 5.494 |
| Idempotent reimport | 2.562 | 2.326 |
| Aggregate exploration | 0.109 | 0.048 |
| Cohort/research artifacts | 0.383 | 0.078 |

Peak whole-process RSS was 506,104 KiB for PostgreSQL and 480,744 KiB for SQLite.
This high-water mark includes validation, import and analysis, not phase-specific
memory. Reimport inserted/updated zero rows in both databases. The research cohort
contained 11 eligible indices and zero positives; `insufficient_data` was retained
without fitted models or scores.

```bash
scripts/generate_synthea.sh "$PWD/data/performance-synthea20" 20
# Activate the base environment and configure a reachable PostgreSQL DATABASE_URL.
python scripts/benchmark.py --csv-dir data/performance-synthea20/csv \
  --output data/benchmark-postgres20 --postgres
python scripts/benchmark.py --csv-dir data/performance-synthea20/csv \
  --output data/benchmark-sqlite20
```

Choose fresh paths. PostgreSQL uses a generated temporary schema and removes only
that schema after measurement; SQLite uses a temporary database. Benchmark evidence
and research artifacts remain in the requested new directory. No shared table or
demo volume is cleared. Input hashes were checked against completed source files.

The loader currently materializes the export and existing table identities in
memory; validation and reference checks are bounded by available RAM. The measured
73,773 accepted records are substantially larger than the 12-row demo, but do not
justify million-row or multi-user claims. Streaming validation, chunked upserts,
query profiling and concurrency studies are future work, not implemented features.
