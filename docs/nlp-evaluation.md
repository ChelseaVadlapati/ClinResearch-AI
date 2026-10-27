# Experimental synthetic NLP evaluation

## Task and provenance

Predict present, negated, uncertain or family assertion for one annotated concept
per short synthetic snippet. The existing deterministic `extract_concepts` baseline
is unchanged. `benchmarks/nlp/assertions-v1.json` contains 72 individually authored
and labeled examples, created separately from `simulate_note` and the extractor:
48 training examples (12/class), 24 held-out examples (6/class). No template
round-trip labels are used. The fixed split was set before running any model.

The coding assistant authored these synthetic annotations. They have **not** had
independent human or clinical annotation review; there is no inter-rater agreement
study. This is a transparent software challenge set, not a clinical NLP benchmark.
The benchmark text is released under CC0-1.0. No authentic notes or patient data.
Duplicate IDs/text across splits and invalid spans fail validation. Near-duplicate
phrasing, tiny samples and author-specific wording limit conclusions.

## Methods and licensing

- Existing sentence-scoped rule extractor: exact concept spans plus assertions.
- CPU baseline: training-only TF-IDF unigram/bigram vocabulary + fixed logistic
  regression, max_iter=2000, random_state=42.
- Experimental transformer: frozen sentence-transformers/all-MiniLM-L6-v2 encoder
  via ONNX Runtime CPU, masked mean pooling and L2 normalization, followed by a
  logistic head fit on training labels only. Max 256 tokens, batch 8, one ONNX
  thread; no transformer fine-tuning or held-out hyperparameter selection.

The upstream model card declares Apache-2.0. The model revision, tokenizer,
model-card and ONNX SHA-256 hashes are fixed in `benchmarks/nlp/model-lock.json`.
Weights remain outside Git. Only pinned public model assets are downloaded, never
clinical data. No remote inference service is used. Pretraining overlap with phrases
is unknown. The transformer classifies assertions only; it does not predict spans.
No NLP output is used as an inpatient-return predictor.

## Reproduce

Keep optional dependencies separate from the application:

```bash
python -m venv .venv-nlp
.venv-nlp/bin/python -m pip install --require-hashes -r requirements-nlp.lock
.venv-nlp/bin/python -m pip install --no-deps -e .
.venv-nlp/bin/python -m clinresearch.nlp.benchmark \
  --output data/nlp-verification-v1 --model-lock benchmarks/nlp/model-lock.json \
  --cache data/models/minilm-v1 --download-model
# Later offline runs omit --download-model and use a NEW output directory.
# Rules + TF-IDF only, using the base application environment:
python -m clinresearch.nlp.benchmark --output data/nlp-baselines-v1
```

Outputs contain per-class precision/recall/F1/support, confusion matrices, explicit
label order, exact rule span metrics, all assertion errors, model/data provenance
and package versions. Missing weights fail explicitly; baseline-only runs say
`transformer_status: not_run`. Existing outputs are never overwritten. The optional
lock constrains base dependencies to the application's lockfile versions.

## Measured local results, 2026-10-27

On the fixed 24-snippet synthetic holdout, with the committed pinned assets:

| Method | Macro precision | Macro recall | Macro F1 | Incorrect assertions |
| --- | ---: | ---: | ---: | ---: |
| Rules | 0.7893 | 0.5833 | 0.5985 | 10/24 |
| TF-IDF + logistic | 0.8125 | 0.7917 | 0.7893 | 5/24 |
| Frozen MiniLM + logistic | 0.8393 | 0.7917 | 0.7641 | 5/24 |

These are actual computed software-benchmark results, **not clinical accuracy**.
The transformer does not outperform the TF-IDF baseline on macro F1 here. Do not
infer superiority or statistical significance from this small set. Rule exact-span
matching was 24/24 predictions and 24/24 gold spans; this controlled vocabulary
coverage is not evidence of general clinical extraction quality. No confidence
interval or real-world performance claim is made.

The complete measured report is `benchmarks/nlp/verified-results-v1.json` with
all errors and hashes. It is a frozen local evidence artifact; fresh reports are
computed, never substituted with these values.

## Error analysis

Rules miss non-enumerated family terms (sister/uncle/grandfather), uncertainty
paraphrases and negation variants. Sentence-wide cue scope incorrectly negates
established heart failure in “No chest pain today; established heart failure
remains under treatment.” The labels intentionally distinguish the target concept
from another clause; there is no general dependency/scope parser.

The learned classifiers also confuse uncertainty, negation and family statements;
consult each actual error in the measured report. Encoder embeddings can represent
topic better than assertion in tiny training sets. More independently reviewed
annotations, document-level grouping, real permitted datasets and external
validation would be necessary for a research performance claim. No test-set tuning
was performed to improve these reported scores.
