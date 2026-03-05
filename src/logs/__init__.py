from __future__ import annotations

from logs.manager import LogManager, log_manager


def configure_logging(level: str | None = None) -> None:
    log_manager.configure(level=level)


def get_logger(name: str):
    return log_manager.get_logger(name)


def write_json_log(name: str, message: str, payload, *, request_id: str | None = None):
    return log_manager.write_json_log(name=name, message=message, payload=payload, request_id=request_id)
