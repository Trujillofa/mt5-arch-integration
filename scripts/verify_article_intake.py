#!/usr/bin/env python3
"""Verify an MQL5.com article-intake record.

Research-adjacent gate: catalog profit-factor is not validation.
Lives in scripts/ (charter / holdout language), not the platform package.
Does not import catalog Expert Advisor source. Does not place orders.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INTAKE_SCHEMA = "mt5-article-intake/v1"
REQUIRED_FIELDS = (
    "schema",
    "article_url",
    "claim_type",
    "independent_python",
    "parity_package",
    "holdout_used_for_selection",
    "decision",
    "reason",
)
CLAIM_TYPES = frozenset({"pf", "pattern", "math"})
PARITY_PACKAGES = frozenset({"none", "htf_fib", "other"})
DECISIONS = frozenset({"adopt", "defer", "reject"})
_SECRET_KEY_RE = re.compile(r"pass(word|wd)|secret|token|api[_-]?key", re.I)
_MQ5_RE = re.compile(r"\.mq5(?:\b|$)", re.I)

ROOT = Path(__file__).resolve().parents[1]
OFFLINE = ROOT / "tests" / "fixtures" / "article_intake" / "valid.json"


class ArticleIntakeError(Exception):
    """Invalid or incomplete article-intake record."""


def _raise(errors: list[str]) -> None:
    preview = "\n  ".join(errors[:20])
    extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
    raise ArticleIntakeError(f"{len(errors)} article-intake error(s):\n  {preview}{extra}")


def _walk_secrets(obj: Any, trail: str, errors: list[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            loc = f"{trail}.{key}" if trail else str(key)
            if _SECRET_KEY_RE.search(str(key)):
                errors.append(f"secret key {loc} is forbidden")
            _walk_secrets(val, loc, errors)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _walk_secrets(val, f"{trail}[{i}]", errors)


def _walk_mq5_strings(obj: Any, trail: str, hits: list[str]) -> None:
    if isinstance(obj, dict):
        for key, val in obj.items():
            loc = f"{trail}.{key}" if trail else str(key)
            _walk_mq5_strings(val, loc, hits)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _walk_mq5_strings(val, f"{trail}[{i}]", hits)
    elif isinstance(obj, str) and _MQ5_RE.search(obj):
        hits.append(f"{trail}={obj!r}")


def _python_path(value: Any, repo_root: Path, errors: list[str]) -> Path | None:
    """Return a resolved .py path, or None when the field is an explicit refuse."""
    if value is False:
        return None
    if value is True or value is None:
        errors.append("independent_python must be a .py path or false")
        return None
    if not isinstance(value, str) or not value.strip():
        errors.append("independent_python must be a .py path or false")
        return None
    raw = value.strip()
    if _MQ5_RE.search(raw):
        errors.append("independent_python must be a .py path, not catalog .mq5")
        return None
    if not raw.endswith(".py"):
        errors.append(f"independent_python must end in .py, got {raw!r}")
        return None
    path = Path(raw)
    loc = path if path.is_absolute() else (repo_root / path)
    if not loc.is_file():
        errors.append(f"independent_python path does not exist: {raw}")
        return None
    return loc.resolve()


def _load_record(path: Path) -> dict[str, Any]:
    loc = Path(path)
    if loc.is_dir():
        loc = loc / "article_intake.json"
        if not loc.is_file():
            loc = path / "valid.json"
    if not loc.is_file():
        raise ArticleIntakeError(f"intake record not found: {path}")
    try:
        raw = json.loads(loc.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArticleIntakeError(f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ArticleIntakeError("intake record must be a JSON object")
    return raw


def verify_intake(path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Load and fail-closed-verify an article-intake record."""
    root = Path(repo_root) if repo_root is not None else ROOT
    record = _load_record(Path(path))
    errors: list[str] = []
    _walk_secrets(record, "", errors)

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field {field}")

    if record.get("schema") != INTAKE_SCHEMA:
        errors.append(f"schema must be {INTAKE_SCHEMA!r}")

    url = record.get("article_url")
    if "article_url" in record:
        if not isinstance(url, str) or not url.strip():
            errors.append("article_url must be a non-empty http(s) URL")
        else:
            parsed = urlparse(url.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append("article_url must be a non-empty http(s) URL")

    claim = record.get("claim_type")
    if "claim_type" in record and claim not in CLAIM_TYPES:
        errors.append(f"claim_type must be one of {sorted(CLAIM_TYPES)}")

    parity = record.get("parity_package")
    if "parity_package" in record and parity not in PARITY_PACKAGES:
        errors.append(f"parity_package must be one of {sorted(PARITY_PACKAGES)}")

    decision = record.get("decision")
    if "decision" in record and decision not in DECISIONS:
        errors.append(f"decision must be one of {sorted(DECISIONS)}")

    reason = record.get("reason")
    if "reason" in record and (not isinstance(reason, str) or not reason.strip()):
        errors.append("reason must be a non-empty string")

    if "holdout_used_for_selection" in record and record["holdout_used_for_selection"] is not False:
        errors.append("holdout_used_for_selection must be false")

    py_path: Path | None = None
    if "independent_python" in record:
        py_path = _python_path(record["independent_python"], root, errors)

    if decision == "adopt" and py_path is None:
        errors.append("decision=adopt requires independent_python")

    mq5_hits: list[str] = []
    _walk_mq5_strings(record, "", mq5_hits)
    if mq5_hits and py_path is None:
        errors.append(
            "catalog .mq5 without independent python: " + "; ".join(mq5_hits[:5])
        )

    if errors:
        _raise(errors)

    return {
        "ok": True,
        "schema": INTAKE_SCHEMA,
        "article_url": url,
        "claim_type": claim,
        "independent_python": False if py_path is None else str(record["independent_python"]),
        "parity_package": parity,
        "holdout_used_for_selection": False,
        "decision": decision,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "record",
        nargs="?",
        default=str(OFFLINE),
        help="intake JSON (default: committed valid fixture)",
    )
    args = parser.parse_args(argv)
    report = verify_intake(Path(args.record))
    print(f"article-intake PASSED {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
