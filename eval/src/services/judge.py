"""
services/judge.py
-----------------
Everything that talks to the Vertex AI judge model:
  - Prompt builders  : assemble structured prompts from MetricTemplate + dataset
  - Judge caller     : call the Vertex AI generative model
  - Response parsers : extract score / pairwise_choice + explanation from raw output
  - Rubric validators: reject wrong rubric key types before hitting the judge
"""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException
from vertexai.generative_models import GenerationConfig, GenerativeModel

from src.models.common import MetricTemplate
from dataclasses import dataclass

# Internal-only result carriers — raw_judge_output is kept here for error
# logging but is NOT part of the API response models in models/response.py
@dataclass
class PointwiseMetricResult:
    metric: str
    score: float
    explanation: str
    raw_judge_output: str

@dataclass
class PairwiseMetricResult:
    metric: str
    pairwise_choice: str
    explanation: str
    raw_judge_output: str

logger = logging.getLogger(__name__)

PAIRWISE_RUBRIC_KEYS = {"a", "same", "b"}


# ──────────────────────────────────────────────
# Rubric validators
# ──────────────────────────────────────────────

def validate_pointwise_metrics(metrics: list[MetricTemplate]) -> None:
    """Reject metrics whose rubric contains pairwise-style A/SAME/B keys."""
    for metric in metrics:
        if not metric.rating_rubric:
            continue
        rubric_keys = {k.strip().lower() for k in metric.rating_rubric.keys()}
        bad = rubric_keys & PAIRWISE_RUBRIC_KEYS
        if bad:
            raise HTTPException(
                status_code=422,
                detail={
                    "metric": metric.name,
                    "error": (
                        "Pointwise rating_rubric must use numeric keys "
                        "(e.g. '5','4','3','2','1'). "
                        f"Found pairwise-style keys: {sorted(bad)}. "
                        "Did you mean to call /api/pairwise instead?"
                    ),
                },
            )


def validate_pairwise_metrics(metrics: list[MetricTemplate]) -> None:
    """Reject metrics whose rubric contains numeric keys instead of A/SAME/B."""
    for metric in metrics:
        if not metric.rating_rubric:
            continue
        rubric_keys = {k.strip().lower() for k in metric.rating_rubric.keys()}
        if any(k.lstrip("-").replace(".", "").isdigit() for k in metric.rating_rubric.keys()):
            raise HTTPException(
                status_code=422,
                detail={
                    "metric": metric.name,
                    "error": (
                        "Pairwise rating_rubric must use 'A', 'SAME', 'B' as keys. "
                        "Found numeric-style keys instead. "
                        "Did you mean to call /api/pointwise instead?"
                    ),
                },
            )


# ──────────────────────────────────────────────
# Prompt builders
# ──────────────────────────────────────────────

def _build_evaluation_block(metric: MetricTemplate, lines: list[str]) -> None:
    """Shared helper: appends Evaluation section to lines in-place."""
    lines.append("# Evaluation")

    if metric.definition:
        lines += [f"## Metric Definition\n{metric.definition}", ""]

    if metric.criteria:
        lines.append("## Criteria")
        for name, desc in metric.criteria.items():
            lines.append(f"{name}: {desc}")
        lines.append("")

    if metric.rating_rubric:
        lines.append("## Rating Rubric")
        for score, label in metric.rating_rubric.items():
            lines.append(f"{score}: {label}")
        lines.append("")

    if metric.few_shot_examples:
        lines.append("## Few-shot Examples")
        for ex in metric.few_shot_examples:
            for k, v in ex.items():
                lines.append(f"{k.capitalize()}: {v}")
            lines.append("")

    if metric.evaluation_steps:
        lines.append("## Evaluation Steps")
        for i, step in enumerate(metric.evaluation_steps, 1):
            lines.append(f"STEP {i}: {step}")
        lines.append("")


def build_pointwise_prompt(metric: MetricTemplate, dataset: dict[str, str]) -> str:
    """
    Assemble a pointwise judge prompt.

    Injects each key listed in metric.input_variables as a labelled section,
    pulling values from the dataset dict.
    """
    lines: list[str] = [
        "# Instruction",
        "You are an expert evaluator. Your task is to evaluate the quality of the "
        "AI-generated output provided below.",
        "Read all inputs carefully, then evaluate based on the Criteria in the "
        "Evaluation section.",
        "Assign a rating following the Rating Rubric and Evaluation Steps. "
        "Give step-by-step explanations and only choose ratings from the Rating Rubric.",
        "",
    ]

    _build_evaluation_block(metric, lines)

    lines.append("# Inputs and AI-generated Output")
    lines.append("## Inputs")

    # Inject each declared input variable as its own labelled section
    for var in metric.input_variables:
        label = var.replace("_", " ").title()
        lines += [f"### {label}\n{dataset[var]}", ""]

    lines += [
        "Output format — you MUST respond with exactly these two lines and nothing else:",
        "SCORE: <numeric value from the Rating Rubric>",
        "EXPLANATION: <your step-by-step reasoning>",
    ]

    return "\n".join(lines)


def build_pairwise_prompt(metric: MetricTemplate, dataset: dict[str, str]) -> str:
    """
    Assemble a pairwise judge prompt.

    Injects shared context keys from metric.input_variables, then adds
    Response A (response_a_key) and Response B (response_b_key) as labelled sections.
    """
    lines: list[str] = [
        "# Instruction",
        "You are an expert evaluator. Your task is to compare the quality of two "
        "AI-generated responses (Response A and Response B).",
        "Read all inputs carefully, judge each response individually, then declare "
        "a winner based on the Criteria and Rating Rubric below.",
        "",
    ]

    _build_evaluation_block(metric, lines)

    lines.append("# Inputs and AI-generated Responses")
    lines.append("## Shared Inputs")

    # Inject shared context variables
    for var in metric.input_variables:
        label = var.replace("_", " ").title()
        lines += [f"### {label}\n{dataset[var]}", ""]

    # Inject the two responses
    lines += [
        "## AI-generated Responses",
        f"### Response A\n{dataset[metric.response_a_key]}",
        "",
        f"### Response B\n{dataset[metric.response_b_key]}",
        "",
    ]

    lines += [
        "Output format — you MUST respond with exactly these two lines and nothing else:",
        "PAIRWISE_CHOICE: A or SAME or B",
        "EXPLANATION: <your step-by-step reasoning>",
    ]

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Judge caller
# ──────────────────────────────────────────────

def call_judge(prompt_text: str, judge_model: str, temperature: float) -> str:
    """Send a prompt to the Vertex AI judge model and return raw text output."""
    logger.debug("── Judge prompt ──────────────────────\n%s", prompt_text)

    model = GenerativeModel(judge_model)
    resp = model.generate_content(
        prompt_text,
        generation_config=GenerationConfig(
            temperature=temperature,
            max_output_tokens=1024,
        ),
    )

    if not resp.candidates:
        raise HTTPException(
            status_code=502,
            detail=(
                "Judge model returned no candidates. "
                "The prompt may have been blocked by safety filters. "
                f"Prompt feedback: {resp.prompt_feedback}"
            ),
        )

    raw = resp.text
    logger.info("── Judge raw output ──────────────────\n%s", raw)
    return raw


# ──────────────────────────────────────────────
# Response parsers
# ──────────────────────────────────────────────

def parse_pointwise(raw: str, metric_name: str) -> PointwiseMetricResult:
    """Extract SCORE and EXPLANATION from judge raw output."""
    cleaned = re.sub(r"\*{1,2}", "", raw)
    score_m = re.search(r"SCORE\s*:\s*(.+)", cleaned, re.IGNORECASE)
    expl_m  = re.search(r"EXPLANATION\s*:\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)

    if not score_m:
        logger.error("[%s] No SCORE in judge output.\nRaw:\n%s", metric_name, raw)
        raise HTTPException(
            status_code=502,
            detail={"metric": metric_name, "error": "Judge returned no parseable SCORE.", "raw_judge_output": raw},
        )

    raw_score_value = score_m.group(1).strip()

    if raw_score_value.upper() in ("A", "SAME", "B"):
        raise HTTPException(
            status_code=422,
            detail={
                "metric": metric_name,
                "error": (
                    f"Judge returned '{raw_score_value}' as SCORE — that is a pairwise verdict. "
                    "rating_rubric must use numeric keys for /api/pointwise."
                ),
                "raw_judge_output": raw,
            },
        )

    try:
        score = float(raw_score_value)
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail={"metric": metric_name, "error": f"Non-numeric SCORE value: '{raw_score_value}'.", "raw_judge_output": raw},
        )

    logger.info("[%s] score=%s", metric_name, score)
    return PointwiseMetricResult(
        metric=metric_name,
        score=score,
        explanation=expl_m.group(1).strip() if expl_m else "",
        raw_judge_output=raw,
    )


def parse_pairwise(raw: str, metric_name: str) -> PairwiseMetricResult:
    """Extract PAIRWISE_CHOICE and EXPLANATION from judge raw output."""
    cleaned = re.sub(r"\*{1,2}", "", raw)
    choice_m = re.search(
        r'PAIRWISE_CHOICE\s*:\s*["\']?\s*(A|SAME|B|\d+)\s*["\']?',
        cleaned, re.IGNORECASE,
    )
    expl_m = re.search(r"EXPLANATION\s*:\s*(.*)", cleaned, re.IGNORECASE | re.DOTALL)

    if not choice_m:
        logger.error("[%s] No PAIRWISE_CHOICE in judge output.\nRaw:\n%s", metric_name, raw)
        raise HTTPException(
            status_code=502,
            detail={"metric": metric_name, "error": "Judge returned no parseable PAIRWISE_CHOICE.", "raw_judge_output": raw},
        )

    raw_choice = choice_m.group(1).strip()

    if raw_choice.lstrip("-").replace(".", "").isdigit():
        raise HTTPException(
            status_code=422,
            detail={
                "metric": metric_name,
                "error": (
                    f"Judge returned numeric '{raw_choice}' as PAIRWISE_CHOICE. "
                    "rating_rubric must use A/SAME/B keys for /api/pairwise."
                ),
                "raw_judge_output": raw,
            },
        )

    logger.info("[%s] pairwise_choice=%s", metric_name, raw_choice.upper())
    return PairwiseMetricResult(
        metric=metric_name,
        pairwise_choice=raw_choice.upper(),
        explanation=expl_m.group(1).strip() if expl_m else "",
        raw_judge_output=raw,
    )