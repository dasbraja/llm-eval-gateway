"""
models/request.py
-----------------
Request body models for both evaluation endpoints.

dataset is now list[dict[str, str]] — pass multiple dataset items
and the judge is called once per item per metric. Summary scores are
aggregated across all items.
"""

from __future__ import annotations

import os
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from src.models.common import MetricTemplate

DEFAULT_JUDGE = os.environ.get("JUDGE_MODEL", "gemini-2.0-flash-001")


class PointwiseRequest(BaseModel):
    """Request body for POST /api/pointwise."""

    dataset: Annotated[
        list[dict[str, str]],
        Field(
            ...,
            min_length=1,
            description=(
                "One or more dataset items to evaluate. Each item is a dict whose keys "
                "must cover all input_variables declared across every metric."
            ),
            examples=[[
                {
                    "instruction": "Summarize in one sentence.",
                    "article": "Climate change is accelerating...",
                    "response": "Climate change is worsening due to human activity.",
                },
                {
                    "instruction": "Summarize in one sentence.",
                    "article": "Ocean temperatures are rising...",
                    "response": "Rising ocean temperatures threaten marine ecosystems.",
                },
            ]],
        ),
    ]
    metrics: Annotated[
        list[MetricTemplate],
        Field(
            ...,
            min_length=1,
            max_length=5,
            description="Between 1 and 5 metric templates to evaluate against.",
        ),
    ]
    judge_model: str = Field(DEFAULT_JUDGE, description="Vertex AI model ID used as the judge.")
    temperature: float = Field(0.0, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def validate(self) -> "PointwiseRequest":
        # Unique metric names
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("Each entry in 'metrics' must have a unique 'name'.")

        # All input_variables must exist in every dataset item
        for idx, item in enumerate(self.dataset):
            for metric in self.metrics:
                missing = [v for v in metric.input_variables if v not in item]
                if missing:
                    raise ValueError(
                        f"dataset[{idx}]: metric '{metric.name}' declares "
                        f"input_variables {missing} that are missing. "
                        f"Available keys: {list(item.keys())}"
                    )
        return self


class PairwiseRequest(BaseModel):
    """Request body for POST /api/pairwise."""

    dataset: Annotated[
        list[dict[str, str]],
        Field(
            ...,
            min_length=1,
            description=(
                "One or more dataset items to compare. Each item is a dict whose keys "
                "must cover all input_variables, response_a_key, and response_b_key "
                "declared across every metric."
            ),
            examples=[[
                {
                    "instruction": "Explain gravity to a 10-year-old.",
                    "model_a": "Gravity is a fundamental force described by Newtonian mechanics.",
                    "model_b": "Gravity is like an invisible magnet pulling everything down!",
                },
                {
                    "instruction": "What is photosynthesis?",
                    "model_a": "Photosynthesis is the process by which plants convert light energy.",
                    "model_b": "Plants make their own food using sunlight — like tiny solar panels!",
                },
            ]],
        ),
    ]
    metrics: Annotated[
        list[MetricTemplate],
        Field(
            ...,
            min_length=1,
            max_length=5,
            description="Between 1 and 5 metric templates to evaluate against.",
        ),
    ]
    judge_model: str = Field(DEFAULT_JUDGE, description="Vertex AI model ID used as the judge.")
    temperature: float = Field(0.0, ge=0.0, le=2.0)

    @model_validator(mode="after")
    def validate(self) -> "PairwiseRequest":
        # Unique metric names
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("Each entry in 'metrics' must have a unique 'name'.")

        for metric in self.metrics:
            # response_a_key and response_b_key are required for pairwise
            if not metric.response_a_key:
                raise ValueError(
                    f"Metric '{metric.name}' is missing 'response_a_key'. "
                    "Required for /api/pairwise."
                )
            if not metric.response_b_key:
                raise ValueError(
                    f"Metric '{metric.name}' is missing 'response_b_key'. "
                    "Required for /api/pairwise."
                )

            # Validate every dataset item
            for idx, item in enumerate(self.dataset):
                for key_field, key_val in [
                    ("response_a_key", metric.response_a_key),
                    ("response_b_key", metric.response_b_key),
                ]:
                    if key_val not in item:
                        raise ValueError(
                            f"dataset[{idx}]: metric '{metric.name}' declares "
                            f"{key_field}='{key_val}' which is missing. "
                            f"Available keys: {list(item.keys())}"
                        )

                missing = [v for v in metric.input_variables if v not in item]
                if missing:
                    raise ValueError(
                        f"dataset[{idx}]: metric '{metric.name}' declares "
                        f"input_variables {missing} that are missing. "
                        f"Available keys: {list(item.keys())}"
                    )

        return self