from __future__ import annotations

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.timeout_seconds = timeout_seconds or float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

    def complete(self, prompt: str) -> str:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.1")),
            },
        }
        req = urllib.request.Request(
            url=f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            logger.info(
                "LLMClient request start model=%s base_url=%s prompt_chars=%d timeout=%.1fs",
                self.model,
                self.base_url,
                len(prompt),
                self.timeout_seconds,
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (socket.timeout, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            elapsed = time.perf_counter() - started
            logger.warning("LLMClient request failed after %.2fs: %s", elapsed, exc)
            # Fail-soft: planner/answer layers already have deterministic fallbacks.
            return ""

        response_text = body.get("response", "")
        elapsed = time.perf_counter() - started
        logger.info("LLMClient request complete in %.2fs response_chars=%d", elapsed, len(str(response_text)))
        return response_text.strip() if isinstance(response_text, str) else ""
