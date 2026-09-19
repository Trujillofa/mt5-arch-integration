#!/usr/bin/env python3
"""Validate SignalRecord JSON against the v1 research schema (stdlib only).

Does not import src/mt5_arch. Does not place orders. Does not open a Kafka socket.
A structurally valid book_mode=live record is not permission to trade.

Usage:
  python3 scripts/verify_kafka_signal_schema.py
  python3 scripts/verify_kafka_signal_schema.py path/to/record.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "research" / "kafka-signal-bus" / "schema" / "signal_record.v1.json"
EXAMPLE_PATH = (
    ROOT / "research" / "kafka-signal-bus" / "schema" / "examples" / "signal_record.paper.v1.json"
)

SCHEMA_VERSION = 1
REQUIRED_FIELDS = (
    "schema_version",
    "symbol",
    "side",
    "timeframe",
    "strategy_id",
    "terminal_id",
    "ts",
    "book_mode",
)
SIDES = frozenset({"buy", "sell", "flat"})
SIGNAL_TYPES = frozenset({"BUY_BIAS", "SELL_BIAS", "FLAT"})
BOOK_MODES = frozenset({"paper", "live"})
PAPER_TOPIC = "mt5.signals.paper.v1"
_SECRET_KEY_RE = re.compile(r"pass(word|wd)|secret|token|api[_-]?key", re.I)
_ORDER_KEY_RE = re.compile(
    r"^(lots|volume|ticket|magic|request_id|order_type|place_order)$",
    re.I,
)
_FORBIDDEN_TOPIC_MARKERS = (
    ".live.",
    "ftmo",
    "fundednext",
    "fundingpips",
    "alphacapital",
    "fortraders",
    "neomaa",
    "wsf",
)


class SignalSchemaError(Exception):
    """Invalid SignalRecord or research-bus config."""


def _raise(errors: list[str]) -> None:
    preview = "\n  ".join(errors[:20])
    extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
    raise SignalSchemaError(f"{len(errors)} signal-schema error(s):\n  {preview}{extra}")


def load_schema(path: Path | None = None) -> dict[str, Any]:
    dest = path or SCHEMA_PATH
    raw = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SignalSchemaError(f"{dest} is not a JSON object")
    return raw


def _walk_forbidden_keys(obj: Any, trail: str, errors: list[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            loc = f"{trail}.{key}" if trail else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                errors.append(f"secret key {loc} is forbidden")
            if trail == "" and _ORDER_KEY_RE.match(str(key)):
                errors.append(f"order-intent key {loc} is forbidden on SignalRecord")
            if loc == "live" and val is True:
                errors.append("boolean live=true is forbidden; use book_mode only")
            _walk_forbidden_keys(val, loc, errors)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _walk_forbidden_keys(val, f"{trail}[{i}]", errors)


def _check_number(
    name: str,
    val: Any,
    errors: list[str],
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if val is None:
        return
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        errors.append(f"{name} must be a number or null")
        return
    if minimum is not None and val < minimum:
        errors.append(f"{name} must be >= {minimum}")
    if maximum is not None and val > maximum:
        errors.append(f"{name} must be <= {maximum}")


def validate_record(obj: Any, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the record if it matches v1. Does not interpret book_mode as a go-live."""
    errors: list[str] = []
    if not isinstance(obj, dict):
        raise SignalSchemaError("SignalRecord must be a JSON object")
    _walk_forbidden_keys(obj, "", errors)

    schema = schema or load_schema()
    required = tuple(schema.get("required") or REQUIRED_FIELDS)
    for field in required:
        if field not in obj:
            errors.append(f"missing required field {field}")

    version = obj.get("schema_version")
    if version != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION} (got {version!r})")

    for field in ("symbol", "timeframe", "strategy_id", "terminal_id", "ts"):
        val = obj.get(field)
        if field in obj and (not isinstance(val, str) or not val.strip()):
            errors.append(f"{field} must be a non-empty string")

    side = obj.get("side")
    if "side" in obj and side not in SIDES:
        errors.append(f"side must be one of {sorted(SIDES)} (got {side!r})")

    book_mode = obj.get("book_mode")
    if "book_mode" in obj and book_mode not in BOOK_MODES:
        errors.append(f"book_mode must be one of {sorted(BOOK_MODES)} (got {book_mode!r})")

    if "signal_type" in obj and obj["signal_type"] not in SIGNAL_TYPES:
        errors.append(
            f"signal_type must be one of {sorted(SIGNAL_TYPES)} (got {obj['signal_type']!r})"
        )

    for name in ("entry", "sl", "tp"):
        if name in obj:
            _check_number(name, obj[name], errors)
    if "confidence" in obj:
        _check_number("confidence", obj["confidence"], errors, minimum=0.0, maximum=1.0)
    if "timestamp_ns" in obj and obj["timestamp_ns"] is not None:
        ts_ns = obj["timestamp_ns"]
        if not isinstance(ts_ns, int) or isinstance(ts_ns, bool) or ts_ns < 0:
            errors.append("timestamp_ns must be a non-negative integer or null")
    if "partition_key" in obj and obj["partition_key"] is not None:
        if not isinstance(obj["partition_key"], str):
            errors.append("partition_key must be a string")
    if "notes" in obj and obj["notes"] is not None and not isinstance(obj["notes"], str):
        errors.append("notes must be a string")

    if errors:
        _raise(errors)
    return obj


def validate_file(path: Path, *, schema: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return validate_record(raw, schema=schema)


def is_paper_topic(topic: str) -> bool:
    name = (topic or "").strip().lower()
    if name != PAPER_TOPIC:
        return False
    return not any(marker in name for marker in _FORBIDDEN_TOPIC_MARKERS if marker != ".live.")


def refuse_non_paper_topic(topic: str) -> None:
    name = (topic or "").strip()
    lowered = name.lower()
    if any(marker in lowered for marker in _FORBIDDEN_TOPIC_MARKERS):
        raise SignalSchemaError(f"refusing non-paper / prop-flavored topic {name!r}")
    if name != PAPER_TOPIC:
        raise SignalSchemaError(
            f"refusing topic {name!r}; research stub only allows {PAPER_TOPIC!r}"
        )


def load_records(path: Path) -> list[dict[str, Any]]:
    """JSON object, JSON array, or JSONL."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise SignalSchemaError(f"{path} is empty")
    if text[0] == "{":
        # JSONL: first non-space is { but file may have more objects
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) > 1 and all(ln.lstrip().startswith("{") for ln in lines):
            return [validate_record(json.loads(ln)) for ln in lines]
        return [validate_record(json.loads(text))]
    if text[0] == "[":
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise SignalSchemaError(f"{path} must be an object, array, or JSONL")
        return [validate_record(item) for item in raw]
    raise SignalSchemaError(f"{path} is not JSON or JSONL")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="JSON / JSONL SignalRecord files (default: committed paper example)",
    )
    args = parser.parse_args(argv)
    schema = load_schema()
    targets = args.paths or [EXAMPLE_PATH]
    for path in targets:
        records = load_records(path)
        for rec in records:
            validate_record(rec, schema=schema)
        print(f"signal-schema PASSED {path} n={len(records)} schema_version={SCHEMA_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
