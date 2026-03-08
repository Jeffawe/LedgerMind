# LedgerMind

LedgerMind is a personal CFO-style financial analysis engine that turns raw transaction data into grounded financial insights and actionable recommendations.

LedgerMind answers personal finance questions like:

“How did I do last month and what should I change?”

Instead of relying on free-form LLM responses, LedgerMind plans and executes deterministic financial tools against normalized transaction and budget data, then generates a structured answer backed by verifiable evidence.

LedgerMind focuses on **reliable AI-assisted financial analysis** through:

- **Tool-first architecture** for deterministic financial calculations  
- **Structured outputs with citations** linking insights to source data  
- **Validation layers** that detect unsupported numbers or assumptions  
- **Local-first model execution** using locally hosted LLMs
## Project Structure

Key directories:

- `src/application/`: orchestration services (`planner`, `tool_executor`, `answer`, `validator`, engine)
- `src/domain/`: Pydantic schemas and core models
- `src/infrastructure/`: provider adapters, LLM client, persistence, policy profile store
- `src/tools/`: tool implementations and registry
- `src/interface/`: CLI and FastAPI entrypoints
- `scripts/actual/`: Python helper functions/CLI bridges for Actual (`actualpy`)
- `tests/`: unit tests

Important flow:

- `interface.cli.build_engine()` builds the engine from planner + tool registry + executor + answer service
- tools are auto-registered via `src/tools/__init__.py`
- transaction-based tools call `infrastructure.get_transactions.get_transactions`
- `ActualLedgerProvider` reads from Actual via Python helpers in `scripts/actual/`

## Requirements

Tested setup:

- Python `3.11.x` (recommended baseline)
- An Actual server instance running (desktop/server)
- Access to your Actual file via `ACTUAL_SYNC_ID` (or `ACTUAL_FILE`)

## Quick Start (Reproducible Setup)

1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

3. Configure environment

```bash
cp .env.example .env
```

Update `.env` with your values:

- `ACTUAL_SERVER_URL`
- `ACTUAL_PASSWORD`
- `ACTUAL_SYNC_ID` (or set `ACTUAL_FILE`)
- `ACTUAL_DATA_DIR` (default `.actual-cache` is fine)

Optional LLM config (for planner/answer generation):

- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `OLLAMA_TIMEOUT_SECONDS`

## Running LedgerMind

### CLI

```bash
python main.py
```

You will be prompted for a message, then LedgerMind prints a structured JSON answer.

### API (FastAPI)

```bash
uvicorn interface.api:app --app-dir src --reload
```

Then open:

- `http://127.0.0.1:8000/` (minimal test UI)
- `http://127.0.0.1:8000/health`

## Current Tools

Examples of registered tools:

- `ledgers.month_summary`
- `ledgers.category_summary`
- `detect.recurring_charges`
- `detect.anomalies`
- `forecast.cashflow_30d`
- `policy.check_recommendation`

## Memory (MVP)

LedgerMind keeps lightweight durable memory for the **answer stage only** (not the planner).

- Memory file path: `memory/memory.json` (override with `LEDGERMIND_MEMORY_FILE`)
- Max entries: `300` by default (override with `LEDGERMIND_MEMORY_MAX_ITEMS`)
- New memory to persist is returned in `EngineAnswer.memory`

Flow:

1. `AnswerService` loads recent memory and passes it to `AnswerLLM`.
2. `AnswerLLM` can return new memory entries in `EngineAnswer.memory`.
3. `AnswerService` appends those entries to the memory file (deduped and bounded).

Manual/offline summarizer:

```bash
python scripts/memory/summarize_memory.py
```

This generates `memory/memory_summary.json` and is intentionally outside the normal request flow.

## Testing

Run the full test suite:

```bash
python -m unittest
```

Run a focused tool test file:

```bash
python -m unittest tests/test_tools_new.py -v
```


## Common Troubleshooting

- `actualpy` import errors:
  - confirm your virtualenv is active
  - run `pip install -r requirements.txt`
- Actual connection/auth errors:
  - verify `ACTUAL_SERVER_URL`, `ACTUAL_PASSWORD`, and `ACTUAL_SYNC_ID` in `.env`
- Empty or broad tool results:
  - check `date_range` in tool args (many analytics tools depend on it).
