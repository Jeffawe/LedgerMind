from __future__ import annotations

import logging
import os
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


log_manager = LogManager.instance()

