# LedgerMind Project Context

## Mission
Build a grounded, preference-aligned financial decision engine on top of real data to deeply understand LLM training and alignment while creating a genuinely useful personal CFO.

## Name
LedgerMind

## Short Description
An open-source, fine-tuned personal CFO that reads a unified financial ledger, uses tools for exact calculations, and provides grounded, actionable financial decisions with consistent structure and preference-aligned advice.

## Core Purpose
Turn raw financial data (actuals + external sources) into:
- Clear insights
- Concrete actions
- Scenario simulations
- Ongoing financial guidance

## Product Pillars
### 1. Unified Ledger Layer
- Single source of truth for transactions, categories, assets/liabilities, recurring bills, and goals.
- The LLM must never guess numbers.

### 2. Tool-First Architecture
- Deterministic functions compute:
  - Category summaries
  - Trend analysis
  - Cashflow forecasts
  - Subscription detection
  - What-if simulations
- Model explains; tools compute.

### 3. Structured Output Format
Every assistant response should include:
- Summary
- Supporting numbers
- 2-3 options
- Recommended action
- Assumptions and confidence

### 4. Fine-Tuning Focus
Train behavior for:
- Interpreting tool output correctly
- Conservative reasoning
- No hallucinated math
- Explicit number citation
- Risk tolerance and budgeting rule alignment

Note: Fine-tuning should not include raw private financial data.

### 5. Preference Optimization (DPO)
Optimize toward:
- Concise > verbose
- Actionable > generic
- Grounded > speculative
- Risk-aware > optimistic

### 6. Evaluation Loop
Track over time:
- Math correctness
- Citation accuracy
- Tool-usage correctness
- Decision quality
- Drift

## Decision Principles
- Deterministic calculations first, narrative second.
- Cite exact values and sources from tools/ledger in every recommendation.
- Default to conservative and downside-aware recommendations.
- If data is missing, state assumptions explicitly before giving advice.

## Current Build Direction
- Initial phase: define architecture and interfaces before model training.
- Build thin vertical slices:
  1. Ingest a small ledger sample
  2. Run deterministic tools
  3. Produce structured decision output
  4. Evaluate outputs with a repeatable rubric

## Working Conventions (Living)
- Keep responses consistent in structure and tone.
- Prefer simple, testable components over abstract frameworks.
- Record major decisions and rationale in the log below.

## Update Log
### 2026-02-20
- Created initial project context file from founder brief.
- Locked in pillars: unified ledger, tool-first compute, structured outputs, fine-tuning + DPO alignment, and evaluation loop.

## Next Context Updates
When we update this file, append:
- Date
- What changed
- Why it changed
- Impact on architecture/training/evaluation
