from __future__ import annotations

import logging
import os
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from threading import Lock
from typing import Any


ANSI_BOLD = "\033[1m"
ANSI_RESET = "\033[0m"


@dataclass(frozen=True)
class ComponentLogger:
    _logger: logging.Logger
    name: str

    def _prefix(self, message: str) -> str:
        return f"{ANSI_BOLD}{self.name}{ANSI_RESET}: {message}"

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.debug(self._prefix(message), *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.info(self._prefix(message), *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.warning(self._prefix(message), *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.error(self._prefix(message), *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._logger.exception(self._prefix(message), *args, **kwargs)


class LogManager:
    _instance: "LogManager | None" = None
    _lock = Lock()
    JSON_LOG_DIR_ENV = "LEDGERMIND_JSON_LOG_DIR"
    JSON_LOG_ENABLED_ENV = "LEDGERMIND_JSON_LOG_ENABLED"

    def __init__(self) -> None:
        self._configured = False

    @classmethod
    def instance(cls) -> "LogManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def configure(self, level: str | None = None) -> None:
        if self._configured:
            return
        log_level = getattr(logging, (level or os.getenv("LOG_LEVEL", "INFO")).upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s %(levelname)s %(message)s",
        )
        self._configured = True

    def get_logger(self, name: str) -> ComponentLogger:
        self.configure()
        return ComponentLogger(logging.getLogger("ledgermind"), name)

    def log(self, level: str, name: str, message: str, *args: Any, **kwargs: Any) -> None:
        logger = self.get_logger(name)
        fn = getattr(logger, level.lower(), logger.info)
        fn(message, *args, **kwargs)

    def write_json_log(
        self,
        name: str,
        message: str,
        payload: Any,
        *,
        request_id: str | None = None,
    ) -> Path | None:
        enabled_raw = os.getenv(self.JSON_LOG_ENABLED_ENV, "true").strip().lower()
        if enabled_raw in {"0", "false", "no", "off"}:
            return None

        base_dir = Path(os.getenv(self.JSON_LOG_DIR_ENV, "logs/json"))
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
        safe_name = self._sanitize(name)
        safe_message = self._sanitize(message)
        req_part = f"{self._sanitize(request_id)}_" if request_id else ""
        filename = f"{req_part}{timestamp}_{safe_name}_{safe_message}.json"
        output_path = base_dir / filename

        document = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "name": name,
            "message": message,
            "request_id": request_id,
            "payload": payload,
        }
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(document, indent=2, default=str))
            return output_path
        except Exception as exc:
            self.get_logger("LogManager").warning("json log write failed path=%s error=%s", output_path, exc)
            return None

    def _sanitize(self, value: str | None) -> str:
        text = (value or "na").strip().lower()
        if not text:
            return "na"
        allowed = []
        for ch in text:
            if ch.isalnum() or ch in {"-", "_"}:
                allowed.append(ch)
            else:
                allowed.append("_")
        return "".join(allowed)[:80]


log_manager = LogManager.instance()
