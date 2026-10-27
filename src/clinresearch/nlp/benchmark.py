"""Fixed-split synthetic assertion evaluation with rules, TF-IDF and frozen MiniLM."""

import argparse
import hashlib
import importlib.metadata
import json
import re
from pathlib import Path

import numpy as np
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import make_pipeline

from clinresearch.research.notes import CONCEPTS, extract_concepts

LABELS = ["present", "negated", "uncertain", "family"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_benchmark(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or data.get("synthetic_only") is not True:
        raise ValueError("Only the versioned synthetic benchmark is supported")
    if not isinstance(data.get("examples"), list) or not data["examples"]:
        raise ValueError("Benchmark examples must be a nonempty list")
    if any(not isinstance(data.get(k), str) for k in ["dataset_version", "provenance"]):
        raise ValueError("Benchmark version and provenance are required")
    seen_ids, seen_text = set(), set()
    for row in data["examples"]:
        if (
            not isinstance(row, dict)
            or any(
                not isinstance(row.get(k), str)
                for k in ["id", "text", "concept", "assertion", "split"]
            )
            or any(type(row.get(k)) is not int for k in ["start", "end"])
        ):
            raise ValueError("Malformed benchmark example")
        text = row["text"]
        if row["id"] in seen_ids or text.casefold().strip() in seen_text:
            raise ValueError("Duplicate ID/text or split leakage")
        seen_ids.add(row["id"])
        seen_text.add(text.casefold().strip())
        if row["assertion"] not in LABELS or row["split"] not in {"train", "test"}:
            raise ValueError("Invalid label or split")
        if row["concept"] not in CONCEPTS or not 0 <= row["start"] < row["end"] <= len(text):
            raise ValueError("Invalid annotated span or concept")
    for split in ["train", "test"]:
        if {r["assertion"] for r in data["examples"] if r["split"] == split} != set(LABELS):
            raise ValueError("Each split must contain every assertion label")
    return data


def prepare_model(manifest: dict, cache: Path, download: bool) -> None:
    if manifest.get("model") != "sentence-transformers/all-MiniLM-L6-v2" or not re.fullmatch(
        r"[a-f0-9]{40}", manifest.get("revision", "")
    ):
        raise ValueError("Unsupported model or unpinned revision")
    expected = {
        "model.onnx": "onnx/model.onnx",
        "tokenizer.json": "tokenizer.json",
        "README.md": "README.md",
    }
    if {item.get("local") for item in manifest["files"]} != set(expected):
        raise ValueError("Invalid model file set")
    for item in manifest["files"]:
        if expected[item["local"]] != item["remote"] or not re.fullmatch(
            r"[a-f0-9]{64}", item["sha256"]
        ):
            raise ValueError("Invalid model file path or hash")
    cache.mkdir(parents=True, exist_ok=True)
    for item in manifest["files"]:
        path = cache / item["local"]
        if path.exists():
            if sha(path) != item["sha256"]:
                raise ValueError("Cached model file does not match pinned SHA-256")
            continue
        if not download:
            raise FileNotFoundError("Pinned model is absent; use --download-model explicitly")
        url = f"https://huggingface.co/{manifest['model']}/resolve/{manifest['revision']}/{item['remote']}"
        pending = path.with_suffix(path.suffix + ".pending")
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with pending.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    handle.write(chunk)
        if sha(pending) != item["sha256"]:
            raise ValueError("Downloaded model SHA-256 mismatch")
        pending.replace(path)


def embeddings(texts: list[str], cache: Path) -> np.ndarray:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(cache / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(
        str(cache / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
    )
    result = []
    for offset in range(0, len(texts), 8):
        batch = tokenizer.encode_batch(texts[offset : offset + 8])
        values = {
            "input_ids": np.array([b.ids for b in batch], dtype=np.int64),
            "attention_mask": np.array([b.attention_mask for b in batch], dtype=np.int64),
            "token_type_ids": np.array([b.type_ids for b in batch], dtype=np.int64),
        }
        hidden = session.run(None, {i.name: values[i.name] for i in session.get_inputs()})[0]
        mask = values["attention_mask"][..., None]
        pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1)
        result.extend(pooled / np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12))
    return np.asarray(result)


def score(truth, predicted) -> dict:
    matrix_labels = LABELS + (["unmatched"] if "unmatched" in predicted else [])
    return {
        "classification": classification_report(
            truth, predicted, labels=LABELS, output_dict=True, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(truth, predicted, labels=matrix_labels).tolist(),
        "label_order": matrix_labels,
    }


def run_benchmark(
    dataset: Path,
    output: Path,
    manifest_path: Path | None = None,
    cache: Path | None = None,
    download: bool = False,
) -> dict:
    if output.exists():
        raise FileExistsError("Output directory already exists")
    data = load_benchmark(dataset)
    train = [r for r in data["examples"] if r["split"] == "train"]
    test = [r for r in data["examples"] if r["split"] == "test"]
    x_train, y_train = [r["text"] for r in train], [r["assertion"] for r in train]
    x_test, y_test = [r["text"] for r in test], [r["assertion"] for r in test]
    # Vocabulary and IDF fit training text only; fixed hyperparameters, no test tuning.
    tfidf = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2)), LogisticRegression(max_iter=2000, random_state=42)
    )
    tfidf.fit(x_train, y_train)
    predicted = {"tfidf_logistic": tfidf.predict(x_test).tolist()}
    rules, span_matches, predicted_spans = [], 0, 0
    for row in test:
        mentions = extract_concepts(row["text"])
        predicted_spans += len(mentions)
        matches = [
            m
            for m in mentions
            if m["start"] == row["start"]
            and m["end"] == row["end"]
            and m["concept"] == row["concept"]
        ]
        span_matches += bool(matches)
        rules.append(matches[0]["assertion"] if matches else "unmatched")
    predicted["rules"] = rules
    model = None
    if manifest_path is not None:
        if cache is None:
            raise ValueError("Transformer requires an explicit cache")
        model = json.loads(manifest_path.read_text())
        prepare_model(model, cache, download)
        # The pretrained encoder is frozen; only the logistic head fits training labels.
        vectors = embeddings(x_train + x_test, cache)
        head = LogisticRegression(max_iter=2000, random_state=42)
        head.fit(vectors[: len(train)], y_train)
        predicted["frozen_minilm_logistic"] = head.predict(vectors[len(train) :]).tolist()
    report = {
        "schema_version": 1,
        "synthetic_only": True,
        "dataset_version": data["dataset_version"],
        "dataset_sha256": sha(dataset),
        "provenance": data["provenance"],
        "train_examples": len(train),
        "test_examples": len(test),
        "task": "Four-way assertion classification of one annotated concept per snippet",
        "seed": 42,
        "model": model,
        "transformer_status": "evaluated" if model else "not_run",
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                ["scikit-learn", "numpy", "onnxruntime", "tokenizers"]
                if model
                else ["scikit-learn", "numpy"]
            )
        },
        "rule_exact_spans": {
            "true_positive": span_matches,
            "predicted": predicted_spans,
            "gold": len(test),
            "precision": span_matches / predicted_spans if predicted_spans else 0.0,
            "recall": span_matches / len(test),
            "f1": 2 * span_matches / (predicted_spans + len(test)),
        },
        "results": {name: score(y_test, labels) for name, labels in predicted.items()},
        "errors": {
            name: [
                {
                    "id": row["id"],
                    "text": row["text"],
                    "expected": row["assertion"],
                    "predicted": label,
                }
                for row, label in zip(test, labels, strict=True)
                if label != row["assertion"]
            ]
            for name, labels in predicted.items()
        },
        "limitations": [
            "Small assistant-authored synthetic benchmark without independent human review.",
            "No clinical NLP accuracy or real-note generalization claim.",
            "Test labels are held out from fitting; pretraining contamination is unknown.",
            "Transformer predicts assertions only, not spans or new clinical concepts.",
            "One annotated mention per snippet; complex document-level relations untested.",
            "No hyperparameter selection or significance testing on this small holdout.",
        ],
    }
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/nlp/assertions-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-lock", type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--download-model", action="store_true")
    args = parser.parse_args()
    try:
        report = run_benchmark(
            args.dataset, args.output, args.model_lock, args.cache, args.download_model
        )
    except (OSError, ValueError, requests.RequestException, ImportError) as exc:
        parser.exit(
            1, f"NLP benchmark not written: {type(exc).__name__}; check inputs/dependencies/cache\n"
        )
    print(
        json.dumps(
            {"transformer_status": report["transformer_status"], "results": report["results"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
