from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from logs import get_logger, write_json_log

logger = get_logger("LLMClient")

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

    def complete(self, prompt: str, *, caller: str = "LLMClient", request_id: str | None = None) -> str:
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
            write_json_log(
                name=caller,
                message="llm_prompt",
                payload={
                    "model": self.model,
                    "base_url": self.base_url,
                    "timeout_seconds": self.timeout_seconds,
                    "prompt": prompt,
                },
                request_id=request_id,
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (socket.timeout, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            elapsed = time.perf_counter() - started
            logger.warning("LLMClient request failed after %.2fs: %s", elapsed, exc)
            write_json_log(
                name=caller,
                message="llm_error",
                payload={
                    "model": self.model,
                    "base_url": self.base_url,
                    "error": str(exc),
                },
                request_id=request_id,
            )
            # Fail-soft: planner/answer layers already have deterministic fallbacks.
            return ""

        response_text = body.get("response", "")
        elapsed = time.perf_counter() - started
        write_json_log(
            name=caller,
            message="llm_response",
            payload={
                "model": self.model,
                "elapsed_seconds": round(elapsed, 3),
                "response": response_text,
            },
            request_id=request_id,
        )
        logger.info("LLMClient request complete in %.2fs response_chars=%d", elapsed, len(str(response_text)))
        return response_text.strip() if isinstance(response_text, str) else ""
