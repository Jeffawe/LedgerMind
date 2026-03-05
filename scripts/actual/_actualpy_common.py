#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

JSON_SENTINEL = "__LEDGERMIND_ACTUAL_JSON__:"
REPO_ROOT = Path(__file__).resolve().parents[2]


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def load_repo_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        log(f"[actual-py] cwd={Path.cwd()} dotenv_path={REPO_ROOT / '.env'}")
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def resolve_data_dir() -> Path:
    raw_data_dir = required_env("ACTUAL_DATA_DIR")
    data_dir = Path(raw_data_dir)
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _base_url_candidates(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    candidates = [base]
    # Some deployments proxy Actual API under /api.
    if not base.endswith("/api"):
        candidates.append(f"{base}/api")
    return candidates


def _is_data_index_404(exc: Exception) -> bool:
    message = str(exc)
    return "data-file-index.txt" in message and "404" in message


@contextmanager
def open_actual_client():
    load_repo_dotenv()

    try:
        from actual import Actual  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "actualpy is not installed. Install with: pip install actualpy python-dotenv"
        ) from exc

    base_url = required_env("ACTUAL_SERVER_URL")
    password = required_env("ACTUAL_PASSWORD")
    file_ref = os.getenv("ACTUAL_FILE") or required_env("ACTUAL_SYNC_ID")
    data_dir = resolve_data_dir()
    encryption_password = os.getenv("ACTUAL_BUDGET_ENCRYPTION_PASSWORD")

    last_exc: Exception | None = None
    for candidate_base_url in _base_url_candidates(base_url):
        log(f"[actual-py] init server={candidate_base_url} dataDir={data_dir}")
        kwargs: dict[str, Any] = {
            "base_url": candidate_base_url,
            "password": password,
            "file": file_ref,
            "data_dir": data_dir,
        }
        if encryption_password:
            # actualpy versions have used different keyword names; try common variants.
            for key in ("encryption_password", "file_password"):
                try_kwargs = dict(kwargs)
                try_kwargs[key] = encryption_password
                try:
                    with Actual(**try_kwargs) as actual:
                        yield actual
                        return
                except TypeError:
                    continue
                except Exception as exc:
                    last_exc = exc
                    if _is_data_index_404(exc) and not candidate_base_url.endswith("/api"):
                        log("[actual-py] data-file-index 404; retrying with /api base path")
                        break
                    raise _rewrite_actual_connection_error(exc, candidate_base_url) from exc
            else:
                log(
                    "[actual-py] encryption password provided, but constructor keyword was not recognized; retrying without it"
                )
            if last_exc is not None and _is_data_index_404(last_exc) and not candidate_base_url.endswith("/api"):
                continue

        try:
            with Actual(**kwargs) as actual:
                yield actual
                return
        except Exception as exc:
            last_exc = exc
            if _is_data_index_404(exc) and not candidate_base_url.endswith("/api"):
                log("[actual-py] data-file-index 404; retrying with /api base path")
                continue
            raise _rewrite_actual_connection_error(exc, candidate_base_url) from exc

    if last_exc is not None:
        raise _rewrite_actual_connection_error(last_exc, base_url) from last_exc
    raise RuntimeError("Unable to initialize Actual client")


def _rewrite_actual_connection_error(exc: Exception, base_url: str) -> RuntimeError:
    message = str(exc)
    if "data-file-index.txt" in message and "404" in message:
        candidate = base_url.rstrip("/")
        alt_hint = ""
        if candidate.endswith(":5007"):
            alt_hint = f" Try '{candidate[:-5]}:5006' if that is your Actual server."
        return RuntimeError(
            "Actual server responded with 404 for '/data-file-index.txt'. "
            f"Check ACTUAL_SERVER_URL in your runtime environment (currently '{base_url}')."
            + alt_hint
        )
    return RuntimeError(message)


def json_default(obj: Any) -> Any:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        return {
            k: v
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    return str(obj)


def emit_json(payload: Any) -> None:
    sys.stdout.write(f"{JSON_SENTINEL}{json.dumps(payload, default=json_default)}\n")


def as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def normalize_query_result(result: Any) -> list[Any]:
    # Some APIs return tuples/lists with a single result set when batching.
    if isinstance(result, tuple):
        if len(result) == 1 and isinstance(result[0], list):
            return list(result[0])
        return list(result)
    if isinstance(result, list):
        if len(result) == 1 and isinstance(result[0], list):
            return list(result[0])
        return result
    return [result] if result is not None else []
