"""
api/pairwise.py
---------------
Route handler for POST /api/pairwise.

Iterates over every (metric, dataset_item) pair, calls the judge once per
combination, and aggregates verdicts into per-metric and overall summaries.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.models.request import PairwiseRequest
from src.models.response import (
    PairwiseDatasetResult,
    PairwiseMetricResults,
    PairwiseResponse,
    PairwiseSummary,
)
from src.services.judge import (
    build_pairwise_prompt,
    call_judge,
    parse_pairwise,
    validate_pairwise_metrics,
)

router = APIRouter()

PAIRWISE_SCORE_MAP: dict[str, int] = {"A": 1, "SAME": 0, "B": -1}


@router.post(
    "/pairwise",
    response_model=PairwiseResponse,
    summary="Pairwise comparison",
    description=(
        "Compare two responses (A vs B) across one or more dataset items against "
        "1–5 inline metric templates. The judge is called once per (metric × dataset item). "
        "Returns per-dataset verdicts grouped by metric, plus per-metric and overall summaries."
    ),
)
def pairwise(req: PairwiseRequest) -> PairwiseResponse:
    validate_pairwise_metrics(req.metrics)

    metric_results: list[PairwiseMetricResults] = []

    for metric in req.metrics:
        dataset_results: list[PairwiseDatasetResult] = []

        for idx, item in enumerate(req.dataset):
            prompt = build_pairwise_prompt(metric, item)
            raw = call_judge(prompt, req.judge_model, req.temperature)
            result = parse_pairwise(raw, metric.name)
            dataset_results.append(
                PairwiseDatasetResult(
                    dataset_index=idx,
                    pairwise_choice=result.pairwise_choice,
                    explanation=result.explanation,
                )
            )

        numeric_scores = [PAIRWISE_SCORE_MAP[r.pairwise_choice] for r in dataset_results]
        mean_score = round(sum(numeric_scores) / len(numeric_scores), 4)
        choice_counts = {
            "A":    sum(1 for r in dataset_results if r.pairwise_choice == "A"),
            "SAME": sum(1 for r in dataset_results if r.pairwise_choice == "SAME"),
            "B":    sum(1 for r in dataset_results if r.pairwise_choice == "B"),
        }

        metric_results.append(
            PairwiseMetricResults(
                metric=metric.name,
                mean_score=mean_score,
                choice_counts=choice_counts,
                per_dataset=dataset_results,
            )
        )

    # Overall summary
    all_scores = [
        PAIRWISE_SCORE_MAP[r.pairwise_choice]
        for mr in metric_results
        for r in mr.per_dataset
    ]
    overall_mean = round(sum(all_scores) / len(all_scores), 4)

    per_metric_mean = {r.metric: r.mean_score for r in metric_results}
    per_metric_choice_counts = {r.metric: r.choice_counts for r in metric_results}

    return PairwiseResponse(
        results=metric_results,
        summary=PairwiseSummary(
            overall_mean_score=overall_mean,
            per_metric_mean=per_metric_mean,
            per_metric_choice_counts=per_metric_choice_counts,
        ),
    )