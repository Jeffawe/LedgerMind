from __future__ import annotations

from logs.manager import LogManager, log_manager


def configure_logging(level: str | None = None) -> None:
    log_manager.configure(level=level)


def get_logger(name: str):
    return log_manager.get_logger(name)
