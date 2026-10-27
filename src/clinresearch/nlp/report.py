"""Validate stored benchmark metrics, exposing no example text or row identifiers."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0, le=1)]
Count = Annotated[int, Field(ge=0)]


class Metrics(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, allow_inf_nan=False, populate_by_name=True
    )
    precision: Probability
    recall: Probability
    f1: Probability = Field(alias="f1-score")
    support: Annotated[float, Field(ge=0)]


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    classification: dict[str, Metrics | Probability]
    confusion_matrix: list[list[Count]]
    label_order: list[str]

    @model_validator(mode="after")
    def valid_matrix(self):
        if self.label_order not in [
            ["present", "negated", "uncertain", "family"],
            ["present", "negated", "uncertain", "family", "unmatched"],
        ]:
            raise ValueError("Invalid assertion label order")
        if len(self.confusion_matrix) != len(self.label_order) or any(
            len(row) != len(self.label_order) for row in self.confusion_matrix
        ):
            raise ValueError("Invalid confusion matrix")
        required = {"present", "negated", "uncertain", "family", "macro avg", "weighted avg"}
        if not required <= set(self.classification) or set(self.classification) - required - {
            "accuracy",
            "micro avg",
        }:
            raise ValueError("Invalid classification metric keys")
        if any(not isinstance(self.classification[k], Metrics) for k in required):
            raise ValueError("Invalid per-class metrics")
        return self


class PublicNLPReport(BaseModel):
    # Intentionally ignore local-only errors/text, model files, and annotation details.
    model_config = ConfigDict(extra="ignore", strict=True, allow_inf_nan=False)
    schema_version: Literal[1]
    synthetic_only: Literal[True]
    dataset_version: str
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    train_examples: Count
    test_examples: Count
    transformer_status: Literal["evaluated", "not_run"]
    results: dict[str, Result]

    @model_validator(mode="after")
    def reconcile(self):
        expected = {"rules", "tfidf_logistic"}
        if self.transformer_status == "evaluated":
            expected.add("frozen_minilm_logistic")
        if set(self.results) != expected:
            raise ValueError("NLP result methods do not match execution status")
        for result in self.results.values():
            if sum(sum(row) for row in result.confusion_matrix) != self.test_examples:
                raise ValueError("NLP matrix does not match holdout size")
            if result.classification["macro avg"].support != self.test_examples:
                raise ValueError("NLP support does not match holdout size")
        return self


def public_report(value: object) -> dict:
    return PublicNLPReport.model_validate(value).model_dump(by_alias=True)
