"""Verify benchmark independence, output provenance and honest optional model state."""

import json
from pathlib import Path

import pytest

from clinresearch.nlp.benchmark import load_benchmark, prepare_model, run_benchmark

DATASET = Path("benchmarks/nlp/assertions-v1.json")


def test_independent_synthetic_splits_and_baseline_results(tmp_path):
    data = load_benchmark(DATASET)
    assert len(data["examples"]) == 72
    report = run_benchmark(DATASET, tmp_path / "run")
    assert report["transformer_status"] == "not_run"
    assert report["model"] is None
    assert set(report["results"]) == {"rules", "tfidf_logistic"}
    assert report["train_examples"] == 48
    assert report["test_examples"] == 24
    for result in report["results"].values():
        assert sum(sum(row) for row in result["confusion_matrix"]) == 24
        assert result["classification"]["macro avg"]["support"] == 24
    assert report["errors"]["rules"]  # challenging scope and cue cases are not hidden
    assert report == run_benchmark(DATASET, tmp_path / "repeat")
    with pytest.raises(FileExistsError):
        run_benchmark(DATASET, tmp_path / "run")


def test_duplicate_text_split_leakage_rejected(tmp_path):
    data = json.loads(DATASET.read_text())
    data["examples"][-1]["text"] = data["examples"][0]["text"]
    path = tmp_path / "leak.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="leakage"):
        load_benchmark(path)


def test_bad_span_rejected(tmp_path):
    data = json.loads(DATASET.read_text())
    data["examples"][0]["end"] = 1000
    path = tmp_path / "span.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="span"):
        load_benchmark(path)


def test_missing_model_no_silent_transformer_substitution(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_benchmark(
            DATASET, tmp_path / "output", Path("benchmarks/nlp/model-lock.json"), tmp_path / "model"
        )
    assert not (tmp_path / "output").exists()


def test_model_hash_and_paths_are_checked(tmp_path):
    manifest = json.loads(Path("benchmarks/nlp/model-lock.json").read_text())
    (tmp_path / "model.onnx").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="SHA-256"):
        prepare_model(manifest, tmp_path, False)
    manifest["files"][0]["local"] = "../outside"
    with pytest.raises(ValueError, match="file set"):
        prepare_model(manifest, tmp_path, True)
