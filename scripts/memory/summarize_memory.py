#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from infrastructure.llm.llm_client import LLMClient
from infrastructure.persistence.memory_store import MemoryStore


def build_prompt(memories: list[dict]) -> str:
    payload = {
        "task": "Summarize durable user memory entries for future financial assistant continuity.",
        "memory_entries": memories,
        "rules": [
            "Return JSON only.",
            "Return one object with keys: summary_bullets (array of strings), stable_preferences (array), constraints (array), goals (array).",
            "Do not include speculative or temporary details.",
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize LedgerMind memory file using the configured LLM.")
    parser.add_argument("--out", default="memory/memory_summary.json", help="Output summary file path")
    parser.add_argument("--limit", type=int, default=300, help="Max memory entries to include in summarization input")
    args = parser.parse_args()

    store = MemoryStore()
    items = store.load_recent(limit=args.limit)
    if not items:
        print("No memory entries found.")
        return 0

    prompt = build_prompt([item.model_dump(mode="json") for item in items])
    llm = LLMClient()
    raw = llm.complete(prompt).strip()
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "input_count": len(items),
        "summary_raw": raw,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote memory summary to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

