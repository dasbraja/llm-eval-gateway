"""
src/eval_mcp/tools.py
----------------
MCP tool implementations for pointwise and pairwise evaluation.

Both tools reuse the same service logic as the FastAPI endpoints
(src/services/judge.py) so behaviour is identical regardless of
whether the caller uses the REST API or the MCP interface.
"""

from __future__ import annotations

import json

from src.models.common import MetricTemplate
from src.models.request import PairwiseRequest, PointwiseRequest
from src.services.judge import (
    build_pairwise_prompt,
    build_pointwise_prompt,
    call_judge,
    parse_pairwise,
    parse_pointwise,
    validate_pairwise_metrics,
    validate_pointwise_metrics,
)
from src.models.response import (
    PairwiseDatasetResult,
    PairwiseMetricResults,
    PairwiseResponse,
    PairwiseSummary,
    PointwiseDatasetResult,
    PointwiseMetricResults,
    PointwiseResponse,
    PointwiseSummary,
)

PAIRWISE_SCORE_MAP: dict[str, int] = {"A": 1, "SAME": 0, "B": -1}


def run_pointwise(
    dataset: list[dict[str, str]],
    metrics: list[dict],
    judge_model: str,
    temperature: float,
) -> str:
    """
    Core logic for pointwise evaluation.
    Accepts raw dicts, parses into typed models, runs evaluation,
    and returns a JSON string so MCP can return it as text content.
    """
    # Parse metric dicts into MetricTemplate models
    parsed_metrics = [MetricTemplate(**m) for m in metrics]

    # Validate request via Pydantic (catches missing input_variables etc.)
    req = PointwiseRequest(
        dataset=dataset,
        metrics=parsed_metrics,
        judge_model=judge_model,
        temperature=temperature,
    )

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

    per_metric_mean = {r.metric: r.mean_score for r in metric_results}
    overall_mean = round(sum(per_metric_mean.values()) / len(per_metric_mean), 4)

    response = PointwiseResponse(
        results=metric_results,
        summary=PointwiseSummary(
            overall_mean_score=overall_mean,
            per_metric_mean=per_metric_mean,
        ),
    )

    return json.dumps(response.model_dump(), indent=2)


def run_pairwise(
    dataset: list[dict[str, str]],
    metrics: list[dict],
    judge_model: str,
    temperature: float,
) -> str:
    """
    Core logic for pairwise evaluation.
    Accepts raw dicts, parses into typed models, runs evaluation,
    and returns a JSON string so MCP can return it as text content.
    """
    parsed_metrics = [MetricTemplate(**m) for m in metrics]

    req = PairwiseRequest(
        dataset=dataset,
        metrics=parsed_metrics,
        judge_model=judge_model,
        temperature=temperature,
    )

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

    all_scores = [
        PAIRWISE_SCORE_MAP[r.pairwise_choice]
        for mr in metric_results
        for r in mr.per_dataset
    ]
    overall_mean = round(sum(all_scores) / len(all_scores), 4)
    per_metric_mean = {r.metric: r.mean_score for r in metric_results}
    per_metric_choice_counts = {r.metric: r.choice_counts for r in metric_results}

    response = PairwiseResponse(
        results=metric_results,
        summary=PairwiseSummary(
            overall_mean_score=overall_mean,
            per_metric_mean=per_metric_mean,
            per_metric_choice_counts=per_metric_choice_counts,
        ),
    )

    return json.dumps(response.model_dump(), indent=2)