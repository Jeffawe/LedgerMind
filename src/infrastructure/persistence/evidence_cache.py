from __future__ import annotations


class EvidenceCache:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def put(self, key: str, value: dict) -> None:
        self._store[key] = value

    def get(self, key: str) -> dict | None:
        return self._store.get(key)
