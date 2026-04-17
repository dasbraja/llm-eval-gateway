"""
api/pointwise.py
----------------
Route handler for POST /api/pointwise.

Iterates over every (metric, dataset_item) pair, calls the judge once per
combination, and aggregates scores into per-metric and overall summaries.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.models.request import PointwiseRequest
from src.models.response import (
    PointwiseDatasetResult,
    PointwiseMetricResults,
    PointwiseResponse,
    PointwiseSummary,
)
from src.services.judge import (
    build_pointwise_prompt,
    call_judge,
    parse_pointwise,
    validate_pointwise_metrics,
)

router = APIRouter()


@router.post(
    "/pointwise",
    response_model=PointwiseResponse,
    summary="Pointwise evaluation",
    description=(
        "Evaluate one or more dataset items against 1–5 inline metric templates. "
        "The judge is called once per (metric × dataset item) combination. "
        "Returns per-dataset scores grouped by metric, plus per-metric and overall mean scores."
    ),
)
def pointwise(req: PointwiseRequest) -> PointwiseResponse:
    validate_pointwise_metrics(req.metrics)

    metric_results: list[PointwiseMetricResults] = []

    for metric in req.metrics:
        dataset_results: list[PointwiseDatasetResult] = []

        for idx, item in enumerate(req.dataset):
            prompt = build_pointwise_prompt(metric, item)
            raw = call_judge(prompt, req.judge_model, req.temperature)
            result = parse_pointwise(raw, metric.name)
            dataset_results.append(
                PointwiseDatasetResult(
                    dataset_index=idx,
                    score=result.score,
                    explanation=result.explanation,
                )
            )

        scores = [r.score for r in dataset_results]
        mean_score = round(sum(scores) / len(scores), 4)

        metric_results.append(
            PointwiseMetricResults(
                metric=metric.name,
                mean_score=mean_score,
                per_dataset=dataset_results,
            )
        )

    # Overall summary
    per_metric_mean = {r.metric: r.mean_score for r in metric_results}
    overall_mean = round(sum(per_metric_mean.values()) / len(per_metric_mean), 4)

    return PointwiseResponse(
        results=metric_results,
        summary=PointwiseSummary(
            overall_mean_score=overall_mean,
            per_metric_mean=per_metric_mean,
        ),
    )