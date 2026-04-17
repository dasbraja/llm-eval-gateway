"""
src/eval_mcp/server.py
-----------------
MCP server definition.

Exposes two tools and a metric template resource catalog:

Tools
-----
  pointwise_eval   — score one or more dataset items against 1-5 metrics
  pairwise_eval    — compare two responses (A vs B) across 1-5 metrics

Resources
---------
  eval://templates/pointwise              — all pointwise template examples (JSON list)
  eval://templates/pairwise               — all pairwise template examples (JSON list)
  eval://templates/pointwise/{name}       — single pointwise template by name
  eval://templates/pairwise/{name}        — single pairwise template by name

Transport
---------
  stdio (default)  — for Claude Desktop / local MCP clients
  SSE              — for remote / browser-based MCP clients
"""

from __future__ import annotations

import json
import os
from typing import Any

import vertexai
from mcp.server.fastmcp import FastMCP

from src.eval_mcp.resources import PAIRWISE_TEMPLATES, POINTWISE_TEMPLATES
from src.eval_mcp.tools import run_pairwise, run_pointwise

# ── Vertex AI init ────────────────────────────
vertexai.init(
    project=os.environ.get("GCP_PROJECT", "bdas-493785"),
    location=os.environ.get("GCP_LOCATION", "us-central1"),
)

DEFAULT_JUDGE = os.environ.get("JUDGE_MODEL", "gemini-2.5-flash")

# ── MCP server instance ───────────────────────
mcp = FastMCP(
    name="GenAI Eval Service",
    instructions=(
        "This server evaluates AI-generated text using Vertex AI as a judge. "
        "Use `pointwise_eval` to score a single response per metric. "
        "Use `pairwise_eval` to compare two responses (A vs B) per metric. "
        "Use `eval://templates/*` resources to discover prebuilt metric templates "
        "you can pass directly to the tools."
    ),
)


# ══════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════

@mcp.tool(
    name="pointwise_eval",
    description=(
        "Evaluate one or more dataset items against 1-5 metric templates using a Vertex AI judge. "
        "Each metric declares which dataset keys to use via `input_variables`. "
        "Returns a numeric score and explanation per dataset item per metric, "
        "plus per-metric and overall mean scores. "
        "Use eval://templates/pointwise to discover prebuilt metric templates."
    ),
)
def pointwise_eval(
    dataset: list[dict[str, str]],
    metrics: list[dict[str, Any]],
    judge_model: str = DEFAULT_JUDGE,
    temperature: float = 0.0,
) -> str:
    """
    Parameters
    ----------
    dataset : list[dict[str, str]]
        One or more evaluation items. Each dict's keys must include all
        `input_variables` declared across every metric.
        Example: [{"instruction": "Summarize...", "response": "The article says..."}]

    metrics : list[dict]
        Between 1 and 5 metric template objects. Each must include:
          - name (str, required)
          - input_variables (list[str]) — dataset keys to inject into the prompt
          - rating_rubric (dict[str, str]) — numeric keys e.g. {"5": "Excellent", "1": "Poor"}
          - criteria, evaluation_steps, definition, few_shot_examples (all optional)
        Tip: fetch a prebuilt template from eval://templates/pointwise/{name}

    judge_model : str
        Vertex AI model ID (default: gemini-2.0-flash-001)

    temperature : float
        Sampling temperature 0.0-2.0 (default: 0.0)

    Returns
    -------
    str
        JSON string containing per-metric results and summary scores.
    """
    return run_pointwise(dataset, metrics, judge_model, temperature)


@mcp.tool(
    name="pairwise_eval",
    description=(
        "Compare two AI responses (A vs B) across one or more dataset items using a Vertex AI judge. "
        "Each metric must declare `response_a_key` and `response_b_key` to identify which dataset "
        "fields hold the two responses. Returns A | SAME | B per dataset item per metric, "
        "plus choice counts and mean scores. "
        "Use eval://templates/pairwise to discover prebuilt metric templates."
    ),
)
def pairwise_eval(
    dataset: list[dict[str, str]],
    metrics: list[dict[str, Any]],
    judge_model: str = DEFAULT_JUDGE,
    temperature: float = 0.0,
) -> str:
    """
    Parameters
    ----------
    dataset : list[dict[str, str]]
        One or more evaluation items. Each dict must include the keys referenced
        by `response_a_key`, `response_b_key`, and all `input_variables`.
        Example: [{"instruction": "...", "model_a": "...", "model_b": "..."}]

    metrics : list[dict]
        Between 1 and 5 metric template objects. Each must include:
          - name (str, required)
          - response_a_key (str, required) — dataset key for Response A
          - response_b_key (str, required) — dataset key for Response B
          - input_variables (list[str]) — shared context keys to inject into the prompt
          - rating_rubric (dict[str, str]) — must use keys "A", "SAME", "B"
          - criteria, evaluation_steps, definition, few_shot_examples (all optional)
        Tip: fetch a prebuilt template from eval://templates/pairwise/{name}

    judge_model : str
        Vertex AI model ID (default: gemini-2.0-flash-001)

    temperature : float
        Sampling temperature 0.0-2.0 (default: 0.0)

    Returns
    -------
    str
        JSON string with per-metric verdicts, choice counts, and summary scores.
    """
    return run_pairwise(dataset, metrics, judge_model, temperature)


# ══════════════════════════════════════════════
# RESOURCES
# ══════════════════════════════════════════════

@mcp.resource("eval://templates/pointwise")
def list_pointwise_templates() -> str:
    """
    Returns all available pointwise metric template examples as a JSON list.
    Templates: fluency, coherence, groundedness, safety, instruction_following,
               verbosity, summarization_quality, question_answering_quality.
    """
    return json.dumps(list(POINTWISE_TEMPLATES.values()), indent=2)


@mcp.resource("eval://templates/pairwise")
def list_pairwise_templates() -> str:
    """
    Returns all available pairwise metric template examples as a JSON list.
    Templates: fluency, coherence, groundedness, safety, instruction_following,
               verbosity, summarization_quality, question_answering_quality.
    """
    return json.dumps(list(PAIRWISE_TEMPLATES.values()), indent=2)


@mcp.resource("eval://templates/pointwise/{name}")
def get_pointwise_template(name: str) -> str:
    """
    Returns a single pointwise metric template by name.
    Available names: fluency, coherence, groundedness, safety,
                     instruction_following, verbosity,
                     summarization_quality, question_answering_quality.
    """
    template = POINTWISE_TEMPLATES.get(name)
    if not template:
        available = list(POINTWISE_TEMPLATES.keys())
        return json.dumps({
            "error": f"Template '{name}' not found.",
            "available": available,
        })
    return json.dumps(template, indent=2)


@mcp.resource("eval://templates/pairwise/{name}")
def get_pairwise_template(name: str) -> str:
    """
    Returns a single pairwise metric template by name.
    Available names: fluency, coherence, groundedness, safety,
                     instruction_following, verbosity,
                     summarization_quality, question_answering_quality.
    """
    template = PAIRWISE_TEMPLATES.get(name)
    if not template:
        available = list(PAIRWISE_TEMPLATES.keys())
        return json.dumps({
            "error": f"Template '{name}' not found.",
            "available": available,
        })
    return json.dumps(template, indent=2)