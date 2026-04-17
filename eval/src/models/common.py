"""
models/common.py
----------------
Shared building blocks used by both pointwise and pairwise request models.

Dataset is now a plain dict[str, str] — any key/value pairs the caller
provides. MetricTemplate declares which keys it needs via input_variables,
and for pairwise, which keys hold the two responses being compared.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field


class MetricTemplate(BaseModel):
    """
    A fully self-contained evaluation rubric.

    input_variables declares which dataset keys to pull into the judge prompt.
    For pairwise metrics, response_a_key and response_b_key identify which
    dataset keys hold the two responses being compared.
    """

    name: str = Field(
        ...,
        description="Unique identifier for this metric, e.g. 'coherence'.",
        examples=["coherence"],
    )
    definition: Optional[str] = Field(
        None,
        description="One-sentence definition of what this metric measures.",
    )
    input_variables: list[str] = Field(
        default_factory=list,
        description=(
            "Ordered list of dataset keys to include in the judge prompt as labelled "
            "input sections. E.g. ['instruction', 'context', 'response']. "
            "For pairwise, list only the shared context keys here — "
            "the two response keys are declared via response_a_key / response_b_key."
        ),
        examples=[["instruction", "context", "response"]],
    )
    response_a_key: Optional[str] = Field(
        None,
        description=(
            "[Pairwise only] Dataset key whose value is Response A (the baseline). "
            "Required when this metric is used on /api/pairwise."
        ),
        examples=["baseline_response"],
    )
    response_b_key: Optional[str] = Field(
        None,
        description=(
            "[Pairwise only] Dataset key whose value is Response B (the candidate). "
            "Required when this metric is used on /api/pairwise."
        ),
        examples=["candidate_response"],
    )
    criteria: Annotated[
        dict[str, str],
        Field(
            description=(
                "Mapping of criterion name -> description. "
                "E.g. {'Coherence': 'Ideas flow logically...'}."
            ),
        ),
    ] = {}
    rating_rubric: Annotated[
        dict[str, str],
        Field(
            description=(
                "Mapping of score -> label. "
                "Pointwise: {'5': 'Excellent', '1': 'Very poor'}. "
                "Pairwise: {'A': 'A is better', 'SAME': 'Equal', 'B': 'B is better'}."
            ),
        ),
    ] = {}
    evaluation_steps: list[str] = Field(
        default_factory=list,
        description="Ordered steps the judge should follow when scoring.",
    )
    few_shot_examples: list[dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Optional few-shot examples. Each item is a dict with keys matching "
            "the input_variables plus 'explanation' and 'score' / 'pairwise_choice'."
        ),
    )