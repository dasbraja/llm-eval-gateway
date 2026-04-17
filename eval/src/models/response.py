"""
models/response.py
------------------
Pydantic response models for the two evaluation endpoints.

Both endpoints now accept a list of datasets, so results are grouped
per metric, each containing one result per dataset item.

Pointwise
---------
  PointwiseDatasetResult   — score + explanation for one dataset item
  PointwiseMetricResults   — all dataset results + mean_score for one metric
  PointwiseSummary         — overall mean + per-metric means across all datasets
  PointwiseResponse        — top-level response envelope

Pairwise
--------
  PairwiseDatasetResult    — choice + explanation for one dataset item
  PairwiseMetricResults    — all dataset results + mean_score + choice_counts for one metric
  PairwiseSummary          — overall mean + per-metric means + per-metric choice counts
  PairwiseResponse         — top-level response envelope
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Pointwise ─────────────────────────────────

class PointwiseDatasetResult(BaseModel):
    dataset_index: int = Field(
        ...,
        description="Zero-based index of the dataset item this result corresponds to.",
    )
    score: float = Field(..., description="Numeric score assigned by the judge.")
    explanation: str = Field(..., description="Step-by-step reasoning from the judge.")


class PointwiseMetricResults(BaseModel):
    metric: str = Field(..., description="Name of the evaluated metric.")
    mean_score: float = Field(
        ...,
        description="Mean score for this metric across all dataset items.",
    )
    per_dataset: list[PointwiseDatasetResult] = Field(
        ...,
        description="Individual result for each dataset item, ordered by dataset_index.",
    )


class PointwiseSummary(BaseModel):
    overall_mean_score: float = Field(
        ...,
        description="Grand mean across all metrics and all dataset items.",
    )
    per_metric_mean: dict[str, float] = Field(
        ...,
        description="Mean score per metric across all dataset items, keyed by metric name.",
    )


class PointwiseResponse(BaseModel):
    results: list[PointwiseMetricResults] = Field(
        ...,
        description="Evaluation results grouped by metric, each containing per-dataset scores.",
    )
    summary: PointwiseSummary = Field(
        ...,
        description="Aggregate summary across all metrics and all dataset items.",
    )


# ── Pairwise ──────────────────────────────────

class PairwiseDatasetResult(BaseModel):
    dataset_index: int = Field(
        ...,
        description="Zero-based index of the dataset item this result corresponds to.",
    )
    pairwise_choice: str = Field(
        ...,
        description="Judge verdict: 'A' (baseline wins), 'SAME' (tie), or 'B' (candidate wins).",
    )
    explanation: str = Field(..., description="Step-by-step reasoning from the judge.")


class PairwiseMetricResults(BaseModel):
    metric: str = Field(..., description="Name of the evaluated metric.")
    mean_score: float = Field(
        ...,
        description=(
            "Mean of numeric-mapped verdicts for this metric across all dataset items. "
            "A=1, SAME=0, B=-1. Positive → A tends to win; Negative → B tends to win."
        ),
    )
    choice_counts: dict[str, int] = Field(
        ...,
        description="Count of A / SAME / B verdicts for this metric across all dataset items.",
    )
    per_dataset: list[PairwiseDatasetResult] = Field(
        ...,
        description="Individual result for each dataset item, ordered by dataset_index.",
    )


class PairwiseSummary(BaseModel):
    overall_mean_score: float = Field(
        ...,
        description=(
            "Grand mean of numeric-mapped verdicts across all metrics and all dataset items. "
            "Positive → A tends to win overall; Negative → B tends to win overall."
        ),
    )
    per_metric_mean: dict[str, float] = Field(
        ...,
        description="Mean numeric score per metric across all dataset items.",
    )
    per_metric_choice_counts: dict[str, dict[str, int]] = Field(
        ...,
        description=(
            "A / SAME / B counts per metric across all dataset items. "
            "E.g. {'fluency': {'A': 3, 'SAME': 1, 'B': 1}}."
        ),
    )


class PairwiseResponse(BaseModel):
    results: list[PairwiseMetricResults] = Field(
        ...,
        description="Comparison results grouped by metric, each containing per-dataset verdicts.",
    )
    summary: PairwiseSummary = Field(
        ...,
        description="Aggregate summary across all metrics and all dataset items.",
    )