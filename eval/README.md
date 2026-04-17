# GenAI Eval Service

LLM evaluation service backed by Vertex AI.  
Two endpoints accept 1–5 fully inline metric templates and a list of dataset items per request.

| Endpoint | Purpose |
|---|---|
| `POST /api/pointwise` | Score one or more responses per metric |
| `POST /api/pairwise` | Compare two responses (A vs B) across one or more dataset items |
| `GET  /health` | Health check |

---

## Project structure

```
llm-eval-gateway/
├── .env.example
├── .gitignore
├── requirements.txt
└── src/
    ├── __init__.py
    ├── bootstrap.py      # FastAPI instance + Vertex AI init
    ├── main.py           # entry point — wires app, router, /health
    ├── router.py         # registers all sub-routers under /api
    ├── api/
    │   ├── __init__.py
    │   ├── pointwise.py  # POST /api/pointwise
    │   └── pairwise.py   # POST /api/pairwise
    ├── models/
    │   ├── __init__.py
    │   ├── common.py     # MetricTemplate
    │   ├── request.py    # PointwiseRequest, PairwiseRequest
    │   └── response.py   # all result / summary / envelope models
    └── services/
        ├── __init__.py
        └── judge.py      # prompt builders, judge caller, response parsers
```

---

## Setup

```bash
# 1. Enter the project
cd llm-eval-gateway

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your GCP_PROJECT, GCP_LOCATION, etc.

# 5. Authenticate with Google Cloud (choose one)
gcloud auth application-default login          # local dev
gcloud auth application-default set-quota-project your-gcp-project-id
# OR
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

## Run

```bash
# From the llm-eval-gateway/ root
uvicorn src.main:app --reload
```

Docs at:
- Swagger UI → http://localhost:8000/docs
- ReDoc      → http://localhost:8000/redoc

---

## Key concepts

### `dataset` — list of items
Both endpoints accept `dataset` as a **list of dicts**. Each dict is one evaluation item.  
The judge is called once per **(metric × dataset item)** combination.

```
             dataset[0]   dataset[1]   dataset[2]
fluency      judge call   judge call   judge call
coherence    judge call   judge call   judge call
```

### `MetricTemplate` — inline rubric
Each metric declares which dataset keys to use via `input_variables`.  
For pairwise, `response_a_key` and `response_b_key` identify the two responses.

### Rubric key rules

| Endpoint | `rating_rubric` keys |
|---|---|
| `/api/pointwise` | Numeric — `"5"`, `"4"`, `"3"`, `"2"`, `"1"` (or `"1"` / `"0"` for binary) |
| `/api/pairwise` | `"A"`, `"SAME"`, `"B"` only |

Mixing these returns a **422** before the judge is called.

---

## Example — `POST /api/pointwise`

Evaluates 2 dataset items across 3 metrics.  
`input_variables` declares which dataset keys each metric injects into the judge prompt.

### Request body

```json
{
  "dataset": [
    {
      "instruction": "Summarize the article in one sentence.",
      "article": "Climate change is accelerating due to human greenhouse gas emissions. Scientists warn that without immediate action, global temperatures could rise by 2°C above pre-industrial levels within decades.",
      "response": "Human greenhouse gas emissions are rapidly accelerating climate change, risking a 2°C temperature rise without urgent action."
    },
    {
      "instruction": "Summarize the article in one sentence.",
      "article": "Ocean temperatures are rising, threatening coral reefs worldwide. Bleaching events have destroyed over 50% of the Great Barrier Reef in the past decade.",
      "response": "Rising ocean temperatures have caused bleaching events that have destroyed more than half of the Great Barrier Reef over the last ten years."
    }
  ],
  "metrics": [
    {
      "name": "groundedness",
      "definition": "Measures whether the response contains only information from the article.",
      "input_variables": ["article", "response"],
      "criteria": {
        "Groundedness": "The response does not introduce facts not present in the article."
      },
      "rating_rubric": {
        "1": "Fully grounded — all content attributable to the article",
        "0": "Not grounded — contains outside or fabricated information"
      },
      "evaluation_steps": [
        "Identify all claims in the response",
        "Check each claim against the article",
        "Score 1 if all grounded, 0 if any are not"
      ]
    },
    {
      "name": "instruction_following",
      "definition": "Measures how well the response satisfies the instruction.",
      "input_variables": ["instruction", "response"],
      "criteria": {
        "Instruction Following": "The response addresses all requirements stated in the instruction."
      },
      "rating_rubric": {
        "5": "Complete fulfillment — all requirements met",
        "4": "Good fulfillment — minor details missed",
        "3": "Partial fulfillment — some requirements ignored",
        "2": "Poor fulfillment — key requirements missed",
        "1": "No fulfillment — instruction was ignored"
      },
      "evaluation_steps": [
        "Identify all explicit requirements in the instruction",
        "Check whether each requirement is satisfied",
        "Score based on the rubric"
      ]
    },
    {
      "name": "fluency",
      "definition": "Measures grammatical correctness and natural flow.",
      "input_variables": ["response"],
      "criteria": {
        "Fluency": "The text is free of grammatical errors and reads naturally and smoothly."
      },
      "rating_rubric": {
        "5": "Completely fluent — no errors, seamless flow",
        "4": "Mostly fluent — very minor issues",
        "3": "Somewhat fluent — noticeable errors",
        "2": "Somewhat inarticulate — frequent errors",
        "1": "Inarticulate — incomprehensible in parts"
      },
      "evaluation_steps": [
        "Check for grammatical and spelling errors",
        "Assess sentence structure and word choice",
        "Score based on the rubric"
      ]
    }
  ],
  "judge_model": "gemini-2.0-flash-001",
  "temperature": 0.0
}
```

### Expected response

```json
{
  "results": [
    {
      "metric": "groundedness",
      "mean_score": 1.0,
      "per_dataset": [
        {
          "dataset_index": 0,
          "score": 1.0,
          "explanation": "All claims in the response are directly attributable to the article..."
        },
        {
          "dataset_index": 1,
          "score": 1.0,
          "explanation": "The response accurately reflects the article's content about coral bleaching..."
        }
      ]
    },
    {
      "metric": "instruction_following",
      "mean_score": 4.5,
      "per_dataset": [
        {
          "dataset_index": 0,
          "score": 5.0,
          "explanation": "The response is exactly one sentence and accurately summarizes the article..."
        },
        {
          "dataset_index": 1,
          "score": 4.0,
          "explanation": "The response is one sentence and covers the key point, though slightly long..."
        }
      ]
    },
    {
      "metric": "fluency",
      "mean_score": 5.0,
      "per_dataset": [
        {
          "dataset_index": 0,
          "score": 5.0,
          "explanation": "The response is grammatically correct with natural flow..."
        },
        {
          "dataset_index": 1,
          "score": 5.0,
          "explanation": "Well-structured sentence, no grammatical issues..."
        }
      ]
    }
  ],
  "summary": {
    "overall_mean_score": 3.5,
    "per_metric_mean": {
      "groundedness": 1.0,
      "instruction_following": 4.5,
      "fluency": 5.0
    }
  }
}
```

---

## Example — `POST /api/pairwise`

Compares two model responses across 2 dataset items against 3 metrics.  
`response_a_key` and `response_b_key` declare which dataset keys hold the two responses.  
`input_variables` lists any additional shared context keys.

### Request body

```json
{
  "dataset": [
    {
      "instruction": "Explain gravity to a 10-year-old.",
      "context": "The explanation should use simple language and a relatable analogy.",
      "model_a": "Gravity is a fundamental force described by Newtonian mechanics that causes objects with mass to attract one another.",
      "model_b": "Gravity is like an invisible magnet that pulls everything toward the ground — that is why when you drop a ball, it always falls down!"
    },
    {
      "instruction": "Explain photosynthesis to a 10-year-old.",
      "context": "The explanation should use simple language and a relatable analogy.",
      "model_a": "Photosynthesis is the biochemical process by which chlorophyll in plant cells absorbs photons and converts CO2 and H2O into glucose.",
      "model_b": "Plants make their own food using sunlight — think of them as tiny solar panels that turn light into energy they can eat!"
    }
  ],
  "metrics": [
    {
      "name": "audience_fit",
      "definition": "Measures how well the response is tailored to a 10-year-old audience.",
      "input_variables": ["instruction", "context"],
      "response_a_key": "model_a",
      "response_b_key": "model_b",
      "criteria": {
        "Audience Fit": "Uses simple language, relatable analogies, and avoids technical jargon."
      },
      "rating_rubric": {
        "A": "Response A is better suited for a 10-year-old",
        "SAME": "Both are equally appropriate for the audience",
        "B": "Response B is better suited for a 10-year-old"
      },
      "evaluation_steps": [
        "Check Response A for jargon and use of analogies",
        "Check Response B for jargon and use of analogies",
        "Determine which a 10-year-old would better understand",
        "Pick the winner"
      ]
    },
    {
      "name": "instruction_following",
      "definition": "Measures how well each response follows the instruction.",
      "input_variables": ["instruction"],
      "response_a_key": "model_a",
      "response_b_key": "model_b",
      "criteria": {
        "Instruction Following": "The response satisfies all explicit requirements in the instruction."
      },
      "rating_rubric": {
        "A": "Response A follows the instruction better",
        "SAME": "Both follow the instruction equally well",
        "B": "Response B follows the instruction better"
      },
      "evaluation_steps": [
        "Identify all requirements in the instruction",
        "Assess how well Response A meets each requirement",
        "Assess how well Response B meets each requirement",
        "Compare and pick the winner"
      ]
    },
    {
      "name": "fluency",
      "definition": "Measures grammatical correctness and natural flow.",
      "input_variables": [],
      "response_a_key": "model_a",
      "response_b_key": "model_b",
      "criteria": {
        "Fluency": "The text is free of grammatical errors and reads naturally."
      },
      "rating_rubric": {
        "A": "Response A is more fluent",
        "SAME": "Both are equally fluent",
        "B": "Response B is more fluent"
      },
      "evaluation_steps": [
        "Analyze fluency of Response A — check grammar and flow",
        "Analyze fluency of Response B — check grammar and flow",
        "Compare and pick the winner"
      ]
    }
  ],
  "judge_model": "gemini-2.0-flash-001",
  "temperature": 0.0
}
```

### Expected response

```json
{
  "results": [
    {
      "metric": "audience_fit",
      "mean_score": -1.0,
      "choice_counts": { "A": 0, "SAME": 0, "B": 2 },
      "per_dataset": [
        {
          "dataset_index": 0,
          "pairwise_choice": "B",
          "explanation": "Response B uses a relatable magnet analogy and avoids terms like 'Newtonian mechanics', making it far more accessible to a 10-year-old..."
        },
        {
          "dataset_index": 1,
          "pairwise_choice": "B",
          "explanation": "Response B uses the solar panel analogy and plain language, while Response A uses biochemical jargon like 'chlorophyll' and 'photons'..."
        }
      ]
    },
    {
      "metric": "instruction_following",
      "mean_score": -0.5,
      "choice_counts": { "A": 0, "SAME": 1, "B": 1 },
      "per_dataset": [
        {
          "dataset_index": 0,
          "pairwise_choice": "B",
          "explanation": "The instruction asked for simple language — Response B satisfies this, Response A does not..."
        },
        {
          "dataset_index": 1,
          "pairwise_choice": "SAME",
          "explanation": "Both responses attempt to explain the concept, though neither perfectly meets all requirements..."
        }
      ]
    },
    {
      "metric": "fluency",
      "mean_score": 0.0,
      "choice_counts": { "A": 0, "SAME": 2, "B": 0 },
      "per_dataset": [
        {
          "dataset_index": 0,
          "pairwise_choice": "SAME",
          "explanation": "Both responses are grammatically correct and read naturally..."
        },
        {
          "dataset_index": 1,
          "pairwise_choice": "SAME",
          "explanation": "Both responses are well-formed with no grammatical issues..."
        }
      ]
    }
  ],
  "summary": {
    "overall_mean_score": -0.5,
    "per_metric_mean": {
      "audience_fit": -1.0,
      "instruction_following": -0.5,
      "fluency": 0.0
    },
    "per_metric_choice_counts": {
      "audience_fit":         { "A": 0, "SAME": 0, "B": 2 },
      "instruction_following": { "A": 0, "SAME": 1, "B": 1 },
      "fluency":               { "A": 0, "SAME": 2, "B": 0 }
    }
  }
}
```

> `mean_score` maps verdicts to numbers: **A=1, SAME=0, B=-1**.  
> `overall_mean_score: -0.5` means Response B tends to win across all metrics and dataset items.

---

## MCP Server

The service also exposes a **Model Context Protocol (MCP)** server so AI assistants
(Claude Desktop, Cursor, etc.) can call the eval tools directly without going through HTTP.

The MCP server reuses the same `services/judge.py` logic as the REST API — behaviour is identical.

### Project structure (MCP additions)

```
llm-eval-gateway/
└── src/
    ├── mcp_main.py           # MCP server entry point
    └── mcp/
        ├── __init__.py
        ├── server.py         # FastMCP instance, tool & resource registrations
        ├── tools.py          # pointwise_eval and pairwise_eval tool logic
        └── resources.py      # metric template catalog (8 pointwise + 8 pairwise)
```

### Tools

| Tool | Description |
|---|---|
| `pointwise_eval` | Score 1+ dataset items against 1–5 metrics. Returns numeric scores + mean. |
| `pairwise_eval` | Compare two responses (A vs B) across 1+ dataset items. Returns A \| SAME \| B + counts. |

### Resources

| URI | Returns |
|---|---|
| `eval://templates/pointwise` | All 8 pointwise template examples as a JSON list |
| `eval://templates/pairwise` | All 8 pairwise template examples as a JSON list |
| `eval://templates/pointwise/{name}` | Single pointwise template by name |
| `eval://templates/pairwise/{name}` | Single pairwise template by name |

Available template names: `fluency`, `coherence`, `groundedness`, `safety`,
`instruction_following`, `verbosity`, `summarization_quality`, `question_answering_quality`

---

### Run MCP server

**Stdio** (Claude Desktop / local clients):
```bash
fastmcp run src/mcp_main.py
```

**SSE** (remote / browser-based clients):
```bash
fastmcp run src/mcp_main.py --transport sse --port 8001
```

Both servers can run simultaneously — FastAPI on port `8000`, MCP on port `8001`.

---

### Connect to Claude Desktop

Add the following to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "genai-eval": {
      "command": "python",
      "args": ["src/mcp_main.py"],
      "cwd": "/Users/brajadas/project/llm-eval-gateway",
      "env": {
        "GCP_PROJECT": "your-gcp-project-id",
        "GCP_LOCATION": "us-central1",
        "JUDGE_MODEL": "gemini-2.0-flash-001",
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
      }
    }
  }
}
```

Restart Claude Desktop — you will see `pointwise_eval` and `pairwise_eval` available as tools.

---

### MCP tool examples

#### `pointwise_eval`

```json
{
  "dataset": [
    {
      "instruction": "Summarize the article in one sentence.",
      "article": "Climate change is accelerating due to human greenhouse gas emissions...",
      "response": "Human greenhouse gas emissions are rapidly accelerating climate change."
    },
    {
      "instruction": "Summarize the article in one sentence.",
      "article": "Ocean temperatures are rising, threatening coral reefs worldwide...",
      "response": "Rising ocean temperatures are putting coral reefs at serious risk."
    }
  ],
  "metrics": [
    {
      "name": "groundedness",
      "definition": "Measures whether the response contains only information from the article.",
      "input_variables": ["article", "response"],
      "criteria": {
        "Groundedness": "The response does not introduce facts not present in the article."
      },
      "rating_rubric": {
        "1": "Fully grounded",
        "0": "Not grounded"
      },
      "evaluation_steps": [
        "Identify all claims in the response",
        "Check each claim against the article",
        "Score 1 if all grounded, 0 if any are not"
      ]
    },
    {
      "name": "fluency",
      "definition": "Measures grammatical correctness and natural flow.",
      "input_variables": ["response"],
      "criteria": {
        "Fluency": "The text is free of grammatical errors and reads naturally."
      },
      "rating_rubric": {
        "5": "Completely fluent",
        "3": "Somewhat fluent",
        "1": "Inarticulate"
      },
      "evaluation_steps": [
        "Check grammar",
        "Assess flow",
        "Score based on rubric"
      ]
    }
  ],
  "judge_model": "gemini-2.0-flash-001",
  "temperature": 0.0
}
```

Or use a prebuilt template from the resource catalog:

```
# First read the template:
eval://templates/pointwise/groundedness

# Then pass it directly to the tool as one of the metrics items.
```

#### `pairwise_eval`

```json
{
  "dataset": [
    {
      "instruction": "Explain gravity to a 10-year-old.",
      "context": "Use simple language and a relatable analogy.",
      "model_a": "Gravity is a fundamental force described by Newtonian mechanics.",
      "model_b": "Gravity is like an invisible magnet pulling everything toward the ground!"
    },
    {
      "instruction": "Explain photosynthesis to a 10-year-old.",
      "context": "Use simple language and a relatable analogy.",
      "model_a": "Photosynthesis is the biochemical process by which chlorophyll absorbs photons.",
      "model_b": "Plants make their own food using sunlight — like tiny solar panels!"
    }
  ],
  "metrics": [
    {
      "name": "audience_fit",
      "definition": "Measures how well the response suits a 10-year-old audience.",
      "input_variables": ["instruction", "context"],
      "response_a_key": "model_a",
      "response_b_key": "model_b",
      "criteria": {
        "Audience Fit": "Uses simple language, relatable analogies, avoids jargon."
      },
      "rating_rubric": {
        "A": "Response A is better suited for a 10-year-old",
        "SAME": "Both are equally appropriate",
        "B": "Response B is better suited for a 10-year-old"
      },
      "evaluation_steps": [
        "Check Response A for jargon and analogies",
        "Check Response B for jargon and analogies",
        "Pick the winner"
      ]
    }
  ],
  "judge_model": "gemini-2.0-flash-001",
  "temperature": 0.0
}
```

---

## MCP Inspector

MCP Inspector is a browser-based UI for testing and debugging MCP servers.
It lets you browse resources, call tools, and inspect inputs/outputs interactively
— without needing Claude Desktop.

### Install

```bash
npx @modelcontextprotocol/inspector
```

No global install needed — `npx` fetches it on first run.

---

### Connect to the eval MCP server

MCP Inspector connects over **SSE**, so start the MCP server in SSE mode first:

**Terminal 1 — start the MCP server**
```bash
cd llm-eval-gateway
export GCP_PROJECT=your-gcp-project-id
export GCP_LOCATION=us-central1
export JUDGE_MODEL=gemini-2.0-flash-001
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

fastmcp run src/mcp_main.py --transport sse --port 8001
```

**Terminal 2 — launch MCP Inspector**
```bash
npx @modelcontextprotocol/inspector
```

Open http://localhost:5173 in your browser.

---

### Connect in the Inspector UI

1. Select transport **SSE**
2. Enter URL: `http://localhost:8001/sse`
3. Click **Connect**

You will see two tabs: **Tools** and **Resources**.

---

### Browse resources

Click the **Resources** tab to see the metric template catalog:

| URI | What you get |
|---|---|
| `eval://templates/pointwise` | All 8 pointwise templates as a JSON list |
| `eval://templates/pairwise` | All 8 pairwise templates as a JSON list |
| `eval://templates/pointwise/fluency` | Single fluency template ready to copy |
| `eval://templates/pairwise/groundedness` | Single groundedness template ready to copy |

Click any resource URI → Inspector fetches and displays the template JSON.  
Copy the template and paste it into the `metrics` array when calling a tool.

---

### Call `pointwise_eval` from Inspector

Click **Tools** → select `pointwise_eval` → MCP Inspector shows each argument as a separate field.

---

#### `dataset`

```json
[
  {
    "instruction": "Summarize the article in one sentence.",
    "article": "Climate change is accelerating due to human greenhouse gas emissions. Scientists warn that without immediate action, global temperatures could rise by 2°C above pre-industrial levels within decades.",
    "response": "Human greenhouse gas emissions are rapidly accelerating climate change, risking a 2°C temperature rise without urgent action."
  },
  {
    "instruction": "Summarize the article in one sentence.",
    "article": "Ocean temperatures are rising, threatening coral reefs worldwide. Bleaching events have destroyed over 50% of the Great Barrier Reef in the past decade.",
    "response": "Rising ocean temperatures have caused bleaching events that destroyed more than half of the Great Barrier Reef over the last ten years."
  }
]
```

#### `metrics`

```json
[
  {
    "name": "groundedness",
    "definition": "Measures whether the response contains only information from the article.",
    "input_variables": ["article", "response"],
    "criteria": {
      "Groundedness": "The response does not introduce facts not present in the article."
    },
    "rating_rubric": {
      "1": "Fully grounded — all content attributable to the article",
      "0": "Not grounded — contains outside or fabricated information"
    },
    "evaluation_steps": [
      "Identify all claims in the response",
      "Check each claim against the article",
      "Score 1 if all grounded, 0 if any are not"
    ]
  },
  {
    "name": "instruction_following",
    "definition": "Measures how well the response satisfies the instruction.",
    "input_variables": ["instruction", "response"],
    "criteria": {
      "Instruction Following": "The response addresses all requirements stated in the instruction."
    },
    "rating_rubric": {
      "5": "Complete fulfillment — all requirements met",
      "4": "Good fulfillment — minor details missed",
      "3": "Partial fulfillment — some requirements ignored",
      "2": "Poor fulfillment — key requirements missed",
      "1": "No fulfillment — instruction was ignored"
    },
    "evaluation_steps": [
      "Identify all explicit requirements in the instruction",
      "Check whether each requirement is satisfied",
      "Score based on the rubric"
    ]
  },
  {
    "name": "fluency",
    "definition": "Measures grammatical correctness and natural flow.",
    "input_variables": ["response"],
    "criteria": {
      "Fluency": "The text is free of grammatical errors and reads naturally and smoothly."
    },
    "rating_rubric": {
      "5": "Completely fluent — no errors, seamless flow",
      "4": "Mostly fluent — very minor issues",
      "3": "Somewhat fluent — noticeable errors",
      "2": "Somewhat inarticulate — frequent errors",
      "1": "Inarticulate — incomprehensible in parts"
    },
    "evaluation_steps": [
      "Check for grammatical and spelling errors",
      "Assess sentence structure and word choice",
      "Score based on the rubric"
    ]
  },
  {
    "name": "verbosity",
    "definition": "Measures whether the response is appropriately concise.",
    "input_variables": ["instruction", "response"],
    "criteria": {
      "Verbosity": "The response covers key points without unnecessary filler or repetition."
    },
    "rating_rubric": {
      "2": "Too verbose — drastically overlong",
      "1": "Somewhat verbose — minor wordiness",
      "0": "Just right — well balanced",
      "-1": "Somewhat brief — missing some useful detail",
      "-2": "Too short — key information is missing"
    },
    "evaluation_steps": [
      "Check whether all key points are covered",
      "Identify any unnecessary repetition or padding",
      "Score based on the rubric"
    ]
  },
  {
    "name": "coherence",
    "definition": "Measures logical flow and organisation of ideas.",
    "input_variables": ["response"],
    "criteria": {
      "Coherence": "Ideas progress logically with clear transitions and consistent focus."
    },
    "rating_rubric": {
      "5": "Completely coherent — seamless logical flow",
      "4": "Mostly coherent — minor gaps",
      "3": "Somewhat coherent — mostly understandable",
      "2": "Somewhat incoherent — weak structure",
      "1": "Incoherent — illogical, no clear organisation"
    },
    "evaluation_steps": [
      "Assess overall structure and progression of ideas",
      "Check transitions between sentences",
      "Score based on the rubric"
    ]
  }
]
```

#### `judge_model`

```
gemini-2.0-flash-001
```

#### `temperature`

```
0.0
```

#### Expected response

```json
{
  "results": [
    {
      "metric": "groundedness",
      "mean_score": 1.0,
      "per_dataset": [
        { "dataset_index": 0, "score": 1.0, "explanation": "All claims are directly attributable to the article..." },
        { "dataset_index": 1, "score": 1.0, "explanation": "The response accurately reflects the coral reef bleaching data..." }
      ]
    },
    {
      "metric": "instruction_following",
      "mean_score": 4.5,
      "per_dataset": [
        { "dataset_index": 0, "score": 5.0, "explanation": "Exactly one sentence, covers key facts as instructed..." },
        { "dataset_index": 1, "score": 4.0, "explanation": "One sentence but slightly long for a single-sentence summary..." }
      ]
    },
    {
      "metric": "fluency",
      "mean_score": 5.0,
      "per_dataset": [
        { "dataset_index": 0, "score": 5.0, "explanation": "Grammatically correct, reads naturally..." },
        { "dataset_index": 1, "score": 5.0, "explanation": "Well-structured, no grammatical issues..." }
      ]
    },
    {
      "metric": "verbosity",
      "mean_score": 0.0,
      "per_dataset": [
        { "dataset_index": 0, "score": 0.0, "explanation": "Well balanced — covers the key point concisely..." },
        { "dataset_index": 1, "score": 0.0, "explanation": "Appropriately concise for the task..." }
      ]
    },
    {
      "metric": "coherence",
      "mean_score": 5.0,
      "per_dataset": [
        { "dataset_index": 0, "score": 5.0, "explanation": "Single sentence flows logically..." },
        { "dataset_index": 1, "score": 5.0, "explanation": "Clear and well-organised..." }
      ]
    }
  ],
  "summary": {
    "overall_mean_score": 3.1,
    "per_metric_mean": {
      "groundedness": 1.0,
      "instruction_following": 4.5,
      "fluency": 5.0,
      "verbosity": 0.0,
      "coherence": 5.0
    }
  }
}
```

---

### Call `pairwise_eval` from Inspector

Click **Tools** → select `pairwise_eval` → fill in each argument separately.

---

#### `dataset`

```json
[
  {
    "instruction": "Explain gravity to a 10-year-old.",
    "context": "Use simple language and a relatable analogy.",
    "model_a": "Gravity is a fundamental force described by Newtonian mechanics that causes objects with mass to attract one another.",
    "model_b": "Gravity is like an invisible magnet that pulls everything toward the ground — that is why when you drop a ball, it always falls down!"
  },
  {
    "instruction": "Explain photosynthesis to a 10-year-old.",
    "context": "Use simple language and a relatable analogy.",
    "model_a": "Photosynthesis is the biochemical process by which chlorophyll in plant cells absorbs photons and converts CO2 and H2O into glucose.",
    "model_b": "Plants make their own food using sunlight — think of them as tiny solar panels that turn light into energy they can eat!"
  }
]
```

#### `metrics`

```json
[
  {
    "name": "audience_fit",
    "definition": "Measures how well the response suits a 10-year-old audience.",
    "input_variables": ["instruction", "context"],
    "response_a_key": "model_a",
    "response_b_key": "model_b",
    "criteria": {
      "Audience Fit": "Uses simple language, relatable analogies, and avoids technical jargon."
    },
    "rating_rubric": {
      "A": "Response A is better suited for a 10-year-old",
      "SAME": "Both are equally appropriate for the audience",
      "B": "Response B is better suited for a 10-year-old"
    },
    "evaluation_steps": [
      "Check Response A for jargon and use of analogies",
      "Check Response B for jargon and use of analogies",
      "Determine which a 10-year-old would better understand",
      "Pick the winner"
    ]
  },
  {
    "name": "instruction_following",
    "definition": "Measures how well each response follows the instruction.",
    "input_variables": ["instruction"],
    "response_a_key": "model_a",
    "response_b_key": "model_b",
    "criteria": {
      "Instruction Following": "The response satisfies all explicit requirements in the instruction."
    },
    "rating_rubric": {
      "A": "Response A follows the instruction better",
      "SAME": "Both follow the instruction equally well",
      "B": "Response B follows the instruction better"
    },
    "evaluation_steps": [
      "Identify all requirements in the instruction",
      "Assess how well Response A meets each requirement",
      "Assess how well Response B meets each requirement",
      "Compare and pick the winner"
    ]
  },
  {
    "name": "fluency",
    "definition": "Measures grammatical correctness and natural flow.",
    "input_variables": [],
    "response_a_key": "model_a",
    "response_b_key": "model_b",
    "criteria": {
      "Fluency": "The text is free of grammatical errors and reads naturally."
    },
    "rating_rubric": {
      "A": "Response A is more fluent",
      "SAME": "Both are equally fluent",
      "B": "Response B is more fluent"
    },
    "evaluation_steps": [
      "Analyze fluency of Response A — check grammar and flow",
      "Analyze fluency of Response B — check grammar and flow",
      "Compare and pick the winner"
    ]
  },
  {
    "name": "coherence",
    "definition": "Measures logical flow and organisation of ideas.",
    "input_variables": [],
    "response_a_key": "model_a",
    "response_b_key": "model_b",
    "criteria": {
      "Coherence": "Ideas progress logically with clear transitions and consistent focus."
    },
    "rating_rubric": {
      "A": "Response A is more coherent",
      "SAME": "Both are equally coherent",
      "B": "Response B is more coherent"
    },
    "evaluation_steps": [
      "Assess the logical flow of Response A",
      "Assess the logical flow of Response B",
      "Compare and pick the winner"
    ]
  },
  {
    "name": "conciseness",
    "definition": "Measures whether the response is appropriately concise.",
    "input_variables": ["instruction"],
    "response_a_key": "model_a",
    "response_b_key": "model_b",
    "criteria": {
      "Conciseness": "The response provides sufficient detail without unnecessary wordiness."
    },
    "rating_rubric": {
      "A": "Response A strikes a better conciseness balance",
      "SAME": "Both are equally concise",
      "B": "Response B strikes a better conciseness balance"
    },
    "evaluation_steps": [
      "Assess completeness and wordiness of Response A",
      "Assess completeness and wordiness of Response B",
      "Compare and pick the winner"
    ]
  }
]
```

#### `judge_model`

```
gemini-2.0-flash-001
```

#### `temperature`

```
0.0
```

#### Expected response

```json
{
  "results": [
    {
      "metric": "audience_fit",
      "mean_score": -1.0,
      "choice_counts": { "A": 0, "SAME": 0, "B": 2 },
      "per_dataset": [
        { "dataset_index": 0, "pairwise_choice": "B", "explanation": "Response B uses a relatable magnet analogy and avoids 'Newtonian mechanics'..." },
        { "dataset_index": 1, "pairwise_choice": "B", "explanation": "Response B avoids 'chlorophyll' and 'photons', uses a solar panel analogy..." }
      ]
    },
    {
      "metric": "instruction_following",
      "mean_score": -0.5,
      "choice_counts": { "A": 0, "SAME": 1, "B": 1 },
      "per_dataset": [
        { "dataset_index": 0, "pairwise_choice": "B", "explanation": "The instruction asked for simple language — Response B complies, Response A does not..." },
        { "dataset_index": 1, "pairwise_choice": "SAME", "explanation": "Both attempt to explain the concept, though neither is perfectly simple..." }
      ]
    },
    {
      "metric": "fluency",
      "mean_score": 0.0,
      "choice_counts": { "A": 0, "SAME": 2, "B": 0 },
      "per_dataset": [
        { "dataset_index": 0, "pairwise_choice": "SAME", "explanation": "Both responses are grammatically correct and read naturally..." },
        { "dataset_index": 1, "pairwise_choice": "SAME", "explanation": "Both are well-formed with no grammatical issues..." }
      ]
    },
    {
      "metric": "coherence",
      "mean_score": 0.0,
      "choice_counts": { "A": 0, "SAME": 2, "B": 0 },
      "per_dataset": [
        { "dataset_index": 0, "pairwise_choice": "SAME", "explanation": "Both present a single clear idea coherently..." },
        { "dataset_index": 1, "pairwise_choice": "SAME", "explanation": "Both responses are equally well-organised..." }
      ]
    },
    {
      "metric": "conciseness",
      "mean_score": 0.0,
      "choice_counts": { "A": 0, "SAME": 2, "B": 0 },
      "per_dataset": [
        { "dataset_index": 0, "pairwise_choice": "SAME", "explanation": "Both responses are similarly concise for the task..." },
        { "dataset_index": 1, "pairwise_choice": "SAME", "explanation": "Neither response is unnecessarily long or too brief..." }
      ]
    }
  ],
  "summary": {
    "overall_mean_score": -0.3,
    "per_metric_mean": {
      "audience_fit": -1.0,
      "instruction_following": -0.5,
      "fluency": 0.0,
      "coherence": 0.0,
      "conciseness": 0.0
    },
    "per_metric_choice_counts": {
      "audience_fit":          { "A": 0, "SAME": 0, "B": 2 },
      "instruction_following": { "A": 0, "SAME": 1, "B": 1 },
      "fluency":               { "A": 0, "SAME": 2, "B": 0 },
      "coherence":             { "A": 0, "SAME": 2, "B": 0 },
      "conciseness":           { "A": 0, "SAME": 2, "B": 0 }
    }
  }
}
```

> `overall_mean_score: -0.3` means Response B tends to win — driven mainly by
> `audience_fit` and `instruction_following`. Response B's use of analogies
> and plain language gives it the edge on the metrics that matter most for this task.

---

### Quick reference — running everything together

```bash
# Terminal 1 — REST API (FastAPI)
uvicorn src.main:app --reload --port 8000

# Terminal 2 — MCP server (SSE for Inspector)
fastmcp run src/mcp_main.py --transport sse --port 8001

# Terminal 3 — MCP Inspector
npx @modelcontextprotocol/inspector

# Then open http://localhost:5173
# Connect to: http://localhost:8001/sse
```

| Interface | URL | Use case |
|---|---|---|
| REST API | http://localhost:8000 | Direct HTTP calls, curl, Python requests |
| Swagger UI | http://localhost:8000/docs | Interactive REST testing |
| MCP (stdio) | — | Claude Desktop, Cursor, local AI clients |
| MCP (SSE) | http://localhost:8001/sse | Remote clients, MCP Inspector |
| MCP Inspector | http://localhost:5173 | Visual tool/resource testing and debugging |