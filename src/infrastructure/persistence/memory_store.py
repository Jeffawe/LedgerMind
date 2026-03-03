from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from domain.schemas import MemoryItem
from logs import get_logger

logger = get_logger("MemoryStore")


class MemoryStore:
    def __init__(self, file_path: str | Path | None = None, max_items: int | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        default_path = repo_root / "memory" / "memory.json"
        self._file_path = Path(file_path) if file_path else Path(os.getenv("LEDGERMIND_MEMORY_FILE", default_path))
        self._max_items = max_items or int(os.getenv("LEDGERMIND_MEMORY_MAX_ITEMS", "300"))

    def load_all(self) -> list[MemoryItem]:
        if not self._file_path.exists():
            return []
        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("failed to read memory file path=%s err=%s", self._file_path, exc)
            return []
        if not isinstance(payload, list):
            return []
        items: list[MemoryItem] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            try:
                items.append(MemoryItem.model_validate(row))
            except Exception:
                continue
        return items

    def load_recent(self, limit: int | None = None) -> list[MemoryItem]:
        items = self.load_all()
        if limit is None or limit <= 0:
            return items
        return items[-limit:]

    def append(self, entries: Iterable[MemoryItem]) -> list[MemoryItem]:
        existing = self.load_all()
        new_entries = [entry for entry in entries if isinstance(entry, MemoryItem) and entry.text.strip()]
        if not new_entries:
            return existing

        seen = {self._fingerprint(item) for item in existing}
        for item in new_entries:
            fp = self._fingerprint(item)
            if fp in seen:
                continue
            existing.append(item)
            seen.add(fp)

        if len(existing) > self._max_items:
            existing = existing[-self._max_items:]

        self._write(existing)
        logger.info("memory updated entries=%d total=%d path=%s", len(new_entries), len(existing), self._file_path)
        return existing

    def _write(self, items: list[MemoryItem]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.model_dump(mode="json") for item in items]
        temp_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self._file_path)

    def _fingerprint(self, item: MemoryItem) -> tuple[str, str]:
        return item.kind.lower(), " ".join(item.text.lower().split())

