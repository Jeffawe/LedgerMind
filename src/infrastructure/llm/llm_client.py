from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from pydantic import BaseModel
from typing import TypeVar, Type, Any

T = TypeVar("T", bound=BaseModel)

from logs import get_logger, write_json_log

logger = get_logger("LLMClient")

class LLMClient:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        self.timeout_seconds = timeout_seconds or float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
        self._client = None
        try:
            import instructor

            provider_model = self.model if "/" in self.model else f"ollama/{self.model}"
            instructor_base_url = self.base_url if self.base_url.endswith("/v1") else f"{self.base_url}/v1"
            self._client = instructor.from_provider(
                provider_model,
                base_url=instructor_base_url,
                mode=instructor.Mode.JSON,
            )
        except Exception as exc:
            logger.exception("LLMClient instructor unavailable; structured calls will use caller fallbacks: %s", exc)

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


    def instruct_complete(
        self,
        prompt: str,
        response_model: Type[T],
        *,
        max_retries: int = 2,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> T:
        if self._client is None:
            raise RuntimeError("Instructor client unavailable")

        timeout = timeout or self.timeout_seconds
        return self._client.create(
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
            max_retries=max_retries,
            timeout=timeout,
            **kwargs,
        )
