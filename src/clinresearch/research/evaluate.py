"""Fixed logistic baseline, temporally purged holdout, and patient bootstrap intervals."""

from datetime import UTC, date, datetime

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from clinresearch.research.cohort import FEATURES, HORIZON
from clinresearch.research.config import StudyConfig

LIMITATIONS = [
    "Synthetic data and simulated notes cannot establish clinical validity or real-world utility.",
    "Outcome is any observed inpatient return within 30 days, not verified unplanned readmission.",
    "Export end assumes complete follow-up; loss to follow-up and outside care are unknown.",
    "Death by the horizon is excluded; competing-risk modeling is not implemented.",
    "One earliest eligible adult discharge per patient changes the target population.",
    "Conditions use onset dates, not entry timestamps; retrospective recording remains a risk.",
    "Fixed baseline and threshold: no holdout tuning, external validation, or fairness claims.",
    "Bootstrap intervals measure sampling variability only, not synthetic-to-real generalization.",
    "Template checks are software tests, not validation on independently annotated notes.",
]


def metrics(y: np.ndarray, probability: np.ndarray) -> dict:
    prediction = probability >= 0.5
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y, probability)),
        "average_precision": float(average_precision_score(y, probability)),
        "brier_score": float(brier_score_loss(y, probability)),
        "sensitivity_at_0_5": float(tp / (tp + fn)),
        "specificity_at_0_5": float(tn / (tn + fp)),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def evaluate(rows: list[dict], split_date: date, config: StudyConfig | None = None) -> dict:
    """No fitting until both partitions contain >=10 patients and >=2 per class.

    These are software guardrails, not a statistical power justification.
    Bootstrap resamples held-out patients with the fitted model fixed.
    """
    config = config or StudyConfig()
    cutoff = datetime.combine(split_date, datetime.min.time(), UTC)
    if len({row["patient_id"] for row in rows}) != len(rows):
        raise ValueError("Cohort must contain exactly one index per patient")
    # Canonical order makes fitted coefficients and bootstrap draws input-order invariant.
    rows = sorted(rows, key=lambda row: (row["discharge"], row["patient_id"]))
    for row in rows:
        if type(row["readmission_30d"]) is not int or row["readmission_30d"] not in (0, 1):
            raise ValueError("Outcome must be the observed binary label 0 or 1")
        values = np.asarray([row[feature] for feature in FEATURES], dtype=float)
        if not np.isfinite(values).all() or (values < 0).any() or row["age"] < 18:
            raise ValueError("Cohort features must be finite, nonnegative, and adult")
    train, test, purged = [], [], []
    for row in rows:
        discharge = datetime.fromisoformat(row["discharge"])
        if discharge.tzinfo is None:
            raise ValueError("Discharge timestamps must include timezone")
        if discharge + HORIZON < cutoff:
            train.append(row)
        elif discharge >= cutoff:
            test.append(row)
        else:
            purged.append(row)
    report = {
        "status": "insufficient_data",
        "features": FEATURES,
        "split_date": split_date.isoformat(),
        "split": {},
        "limitations": LIMITATIONS,
        "threshold": 0.5,
        "method": "StandardScaler + LogisticRegression(C=1, max_iter=2000, random_state=42)",
        "sklearn_version": sklearn.__version__,
        "reason": f"Each partition needs >={config.min_partition_patients} patients "
        f"and >={config.min_partition_class_count} outcomes of each class.",
    }
    for name, partition in [("train", train), ("test", test), ("purged", purged)]:
        report["split"][name] = {
            "patients": len(partition),
            "positives": sum(r["readmission_30d"] for r in partition),
            "discharge_min": min((r["discharge"] for r in partition), default=None),
            "discharge_max": max((r["discharge"] for r in partition), default=None),
        }
    if any(
        len(partition) < config.min_partition_patients
        or min(sum(r["readmission_30d"] == label for r in partition) for label in [0, 1])
        < config.min_partition_class_count
        for partition in [train, test]
    ):
        return report
    x_train = np.array([[r[f] for f in FEATURES] for r in train], dtype=float)
    x_test = np.array([[r[f] for f in FEATURES] for r in test], dtype=float)
    y_train = np.array([r["readmission_30d"] for r in train])
    y_test = np.array([r["readmission_30d"] for r in test])
    pipeline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=42))
    pipeline.fit(x_train, y_train)
    probability = pipeline.predict_proba(x_test)[:, 1]
    scores = metrics(y_test, probability)
    rng = np.random.default_rng(42)
    bootstrap = []
    for _ in range(500):
        indices = rng.integers(0, len(test), len(test))
        if len(np.unique(y_test[indices])) == 2:
            bootstrap.append(metrics(y_test[indices], probability[indices]))
    intervals = {
        key: [float(v) for v in np.quantile([r[key] for r in bootstrap], [0.025, 0.975])]
        for key in ["roc_auc", "average_precision", "brier_score"]
    }
    calibration = []
    for lower, upper in zip(np.arange(0, 1, 0.2), np.arange(0.2, 1.2, 0.2), strict=True):
        mask = (probability >= lower) & (probability < upper if upper < 1 else probability <= 1)
        calibration.append(
            {
                "lower": float(lower),
                "upper": float(min(upper, 1)),
                "count": int(mask.sum()),
                "mean_prediction": float(probability[mask].mean()) if mask.any() else None,
                "observed_fraction": float(y_test[mask].mean()) if mask.any() else None,
            }
        )
    scaler = pipeline.named_steps["standardscaler"]
    model = pipeline.named_steps["logisticregression"]
    report.update(
        {
            "status": "evaluated",
            "reason": None,
            "metrics": scores,
            "bootstrap_95_percent_intervals": intervals,
            "bootstrap_valid_replicates": len(bootstrap),
            "test_prevalence": float(y_test.mean()),
            "train_prevalence": float(y_train.mean()),
            "constant_baseline": metrics(y_test, np.full(len(test), y_train.mean())),
            "calibration": calibration,
            "model": {
                "feature_order": FEATURES,
                "mean": scaler.mean_.tolist(),
                "scale": scaler.scale_.tolist(),
                "coefficients": model.coef_[0].tolist(),
                "intercept": float(model.intercept_[0]),
            },
        }
    )
    return report
