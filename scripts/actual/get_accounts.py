#!/usr/bin/env python3
from __future__ import annotations

import sys

try:
    from ._actualpy_common import emit_json, log, normalize_query_result, open_actual_client
except ImportError:
    from _actualpy_common import emit_json, log, normalize_query_result, open_actual_client


def fetch_accounts() -> list[object]:
    from actual.queries import get_accounts  # type: ignore

    with open_actual_client() as actual:
        log("[actual-py] get_accounts")
        return normalize_query_result(get_accounts(actual.session))


def main() -> int:
    try:
        emit_json(fetch_accounts())
        return 0
    except Exception as exc:
        print(f"[actual-py] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
