"""Validate saved aggregate reports before exposing them to the dashboard."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clinresearch.research.config import StudyConfig

Count = Annotated[int, Field(ge=0)]
Probability = Annotated[float, Field(ge=0, le=1)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Partition(Contract):
    patients: Count
    positives: Count
    discharge_min: str | None
    discharge_max: str | None

    @model_validator(mode="after")
    def valid_counts(self):
        if self.positives > self.patients:
            raise ValueError("Positive outcomes exceed partition size")
        return self


class Split(Contract):
    train: Partition
    test: Partition
    purged: Partition


class Evaluation(Contract):
    status: Literal["insufficient_data", "evaluated"]
    features: list[str]
    split_date: str
    split: Split
    limitations: list[str]
    threshold: Probability
    method: str
    sklearn_version: str
    reason: str | None


class InsufficientEvaluation(Evaluation):
    status: Literal["insufficient_data"]
    reason: str


class Confusion(Contract):
    tn: Count
    fp: Count
    fn: Count
    tp: Count


class Scores(Contract):
    roc_auc: Probability
    average_precision: Probability
    brier_score: Probability
    sensitivity_at_0_5: Probability
    specificity_at_0_5: Probability
    confusion_matrix: Confusion


class Intervals(Contract):
    roc_auc: list[Probability] = Field(min_length=2, max_length=2)
    average_precision: list[Probability] = Field(min_length=2, max_length=2)
    brier_score: list[Probability] = Field(min_length=2, max_length=2)


class CalibrationBin(Contract):
    lower: Probability
    upper: Probability
    count: Count
    mean_prediction: Probability | None
    observed_fraction: Probability | None


class Coefficients(Contract):
    feature_order: list[str]
    mean: list[float]
    scale: list[float]
    coefficients: list[float]
    intercept: float


class EvaluatedEvaluation(Evaluation):
    status: Literal["evaluated"]
    reason: None
    metrics: Scores
    bootstrap_95_percent_intervals: Intervals
    bootstrap_valid_replicates: Count
    test_prevalence: Probability
    train_prevalence: Probability
    constant_baseline: Scores
    calibration: list[CalibrationBin]
    model: Coefficients

    @model_validator(mode="after")
    def adequate_partitions(self):
        for partition in (self.split.train, self.split.test):
            if (
                partition.patients < 10
                or min(partition.positives, partition.patients - partition.positives) < 2
            ):
                raise ValueError("Evaluated report has insufficient outcomes")
        return self


class Notes(Contract):
    count: Count
    template_version: str
    present_concept_mentions: dict[str, Count]


class FlowRow(Contract):
    unit: Literal["record", "episode", "patient"]
    disposition: str
    count: Count


class HistogramBin(Contract):
    lower: float
    upper: float
    count: Count


class FeatureSummary(Contract):
    observed: Count
    missing: Count
    minimum: float | None
    q25: float | None
    median: float | None
    q75: float | None
    maximum: float | None
    histogram: list[HistogramBin]

    @model_validator(mode="after")
    def reconcile(self):
        if sum(b.count for b in self.histogram) != self.observed:
            raise ValueError("Histogram count mismatch")
        values = [self.minimum, self.q25, self.median, self.q75, self.maximum]
        if self.observed:
            if any(v is None for v in values) or values != sorted(values):
                raise ValueError("Invalid feature quantiles")
        elif any(v is not None for v in values):
            raise ValueError("Empty feature cannot have quantiles")
        return self


class Descriptive(Contract):
    patients: Count
    positives: Count
    negatives: Count
    outcome_fraction: Probability | None
    outcome_wilson_95: list[Probability] | None
    interval_withheld_reason: str | None
    features: dict[str, FeatureSummary]
    interpretation: str

    @model_validator(mode="after")
    def reconcile(self):
        from clinresearch.research.cohort import FEATURES

        if self.positives + self.negatives != self.patients:
            raise ValueError("Descriptive class counts do not reconcile")
        expected = self.positives / self.patients if self.patients else None
        if self.outcome_fraction != expected or set(self.features) != set(FEATURES):
            raise ValueError("Invalid descriptive outcome or feature set")
        if any(f.observed + f.missing != self.patients for f in self.features.values()):
            raise ValueError("Feature missingness does not reconcile")
        if self.outcome_wilson_95 is not None:
            if self.patients < 20 or min(self.positives, self.negatives) < 2:
                raise ValueError("Insufficient observations for displayed interval")
            if len(self.outcome_wilson_95) != 2 or self.outcome_wilson_95 != sorted(
                self.outcome_wilson_95
            ):
                raise ValueError("Invalid descriptive interval")
        return self


class ResearchReport(Contract):
    schema_version: Literal[1]
    synthetic_only: Literal[True]
    generated_at: str
    cohort_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_end_exclusive: str
    cohort_audit: dict[str, Count]
    cohort_flow: list[FlowRow] | None = None
    protocol_version: str | None = None
    study_config: StudyConfig | None = None
    config_sha256: str | None = None
    descriptive: Descriptive | None = None
    notes: Notes
    evaluation: Annotated[
        InsufficientEvaluation | EvaluatedEvaluation, Field(discriminator="status")
    ]

    @model_validator(mode="after")
    def valid_provenance(self):
        if datetime.fromisoformat(self.generated_at).tzinfo is None:
            raise ValueError("Report timestamp must include timezone")
        if date.fromisoformat(self.evaluation.split_date) >= date.fromisoformat(
            self.observation_end_exclusive
        ):
            raise ValueError("Split must precede observation end")
        if self.cohort_flow is not None:
            from clinresearch.research.run import cohort_flow

            expected = cohort_flow(self.cohort_audit)
            if [row.model_dump() for row in self.cohort_flow] != expected:
                raise ValueError("Saved cohort flow does not match audit")
        partitions = (
            self.evaluation.split.train,
            self.evaluation.split.test,
            self.evaluation.split.purged,
        )
        if sum(part.patients for part in partitions) != self.cohort_audit["eligible_patients"]:
            raise ValueError("Split counts do not match cohort")
        if sum(part.positives for part in partitions) != self.cohort_audit["positive_outcomes"]:
            raise ValueError("Split outcomes do not match cohort")
        if self.study_config is not None:
            if self.config_sha256 != self.study_config.fingerprint():
                raise ValueError("Study configuration fingerprint mismatch")
            if self.evaluation.status == "evaluated":
                for part in partitions[:2]:
                    if (
                        part.patients < self.study_config.min_partition_patients
                        or min(part.positives, part.patients - part.positives)
                        < self.study_config.min_partition_class_count
                    ):
                        raise ValueError("Evaluated report violates configured sufficiency")
        if self.descriptive is not None and (
            self.descriptive.patients != self.cohort_audit["eligible_patients"]
            or self.descriptive.positives != self.cohort_audit["positive_outcomes"]
        ):
            raise ValueError("Descriptive counts do not match cohort")
        if self.notes.count != self.cohort_audit["eligible_patients"]:
            raise ValueError("Note count does not match cohort")
        return self


def validate_report(value: object) -> dict:
    """Reject unknown fields, incomplete nested data, nonfinite scores, and false provenance."""
    return ResearchReport.model_validate(value).model_dump(exclude_unset=True)
