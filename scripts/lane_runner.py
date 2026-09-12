"""lane_runner — thin CLI over lane_kit for pre-registered lanes.

Executes a queue of committed locks. Does **not** simulate families (lanes
own clocks); it validates the lock, dispatches to a lane-local ``run_screen``,
stamps lock/data/commit digests, and appends one JSONL verdict.

Refusals (fail closed):
- lock file not in HEAD, or working tree blob ≠ HEAD blob (dirty/uncommitted)
- promote/live_go flips, cost-book drift, data sha mismatch
- holdout.start missing, or a taken holdout that is not THIS lock's own start
- grid cardinality ≠ lock ``expected_configs``

Ledger: ``results/lane_verdicts.jsonl`` (create if missing, never rewrite).
Same ``search_id+lock_sha256+code_commit`` does not duplicate-append.

Run with plain python3 (host numpy/pandas via lane_kit), never uv run::

    python3 scripts/lane_runner.py --lock results/foo_lock.json --out /tmp/out
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lane_kit as lk  # noqa: E402

__all__ = [
    "TAKEN_HOLDOUTS",
    "HOLDOUT_OWNERS",
    "LEDGER_NAME",
    "require_committed_lock",
    "validate_lane_lock",
    "resolve_runner_module",
    "append_verdict",
    "verdict_row",
    "run_lane",
    "main",
]

LEDGER_NAME = "results/lane_verdicts.jsonl"

# Holdouts already burned. A lock's *own* start is allowed (this lane's
# holdout); a NEW lock may not reuse another lane's start.
TAKEN_HOLDOUTS = frozenset(
    {
        date(2025, 3, 1),
        date(2026, 1, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
    }
)

HOLDOUT_OWNERS: dict[str, str] = {
    "2025-03-01": "eurusd_ny_scalp_develop_v1",
    "2026-01-01": "xau_session_scalp",
    "2026-03-01": "btc_ny_session_scalp_develop_v1",
    "2026-04-01": "btc_trend_pullback_develop_v1",
    "2026-06-01": "us_index_session_develop_v1",
    "2026-07-01": "us_index_session_v8",
}

# search_id prefix -> lane-local module that exports run_screen(lock) -> dict
RUNNER_REGISTRY: tuple[tuple[str, str], ...] = (
    ("btc_trend_pullback", "btc_trend_pullback_autoresearch"),
    ("btc_ny_session_scalp", "btc_ny_session_scalp_autoresearch"),
)

_BNS_MODULE = "btc_ny_session_scalp_autoresearch"


class RunnerMissingError(Exception):
    """Lane-local runner module is not importable in this tree."""

    def __init__(self, module: str) -> None:
        super().__init__(module)
        self.module = module


def _git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def git_toplevel(start: Path) -> Path:
    """Repo root containing ``start`` (file or directory)."""
    probe = start if start.is_dir() else start.parent
    r = _git(probe, "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        raise SystemExit(f"not a git repo: {probe} ({r.stderr.strip()})")
    return Path(r.stdout.strip())


def require_committed_lock(lock_path: Path, repo: Path | None = None) -> dict[str, str]:
    """Refuse an untracked, uncommitted, or dirty lock.

    ``git ls-files --error-unmatch`` plus HEAD blob sha must equal the
    working-tree ``git hash-object``. Dirty lock = refuse.
    """
    path = lock_path.resolve()
    if not path.is_file():
        raise SystemExit(f"lock not found: {path}")
    repo = git_toplevel(path) if repo is None else Path(repo).resolve()
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError as e:
        raise SystemExit(f"lock {path} is outside repo {repo}") from e
    listed = _git(repo, "ls-files", "--error-unmatch", "--", rel)
    if listed.returncode != 0:
        raise SystemExit(f"lock is not committed (untracked): {rel}")
    head = _git(repo, "rev-parse", f"HEAD:{rel}")
    if head.returncode != 0:
        raise SystemExit(f"lock is not committed (not in HEAD): {rel}")
    work = _git(repo, "hash-object", "--", str(path))
    if work.returncode != 0:
        raise SystemExit(f"hash-object failed for {rel}: {work.stderr.strip()}")
    head_blob = head.stdout.strip()
    work_blob = work.stdout.strip()
    if head_blob != work_blob:
        raise SystemExit(f"lock is dirty vs HEAD: {rel}")
    commit = _git(repo, "rev-parse", "HEAD")
    if commit.returncode != 0:
        raise SystemExit("cannot read HEAD")
    return {
        "rel": rel,
        "lock_sha256": lk.sha256_file(path),
        "code_commit": commit.stdout.strip(),
        "head_blob": head_blob,
        "repo": str(repo),
    }


def _assert_runner_holdout(lock: Mapping[str, Any]) -> date:
    """Own holdout.start is allowed; a NEW lock cannot steal a taken start."""
    try:
        raw = lock["holdout"]["start"]
    except (KeyError, TypeError) as e:
        raise SystemExit("lock missing holdout.start") from e
    hs = date.fromisoformat(str(raw))
    sid = str(lock.get("search_id") or "")
    owner = HOLDOUT_OWNERS.get(hs.isoformat())
    forbidden = TAKEN_HOLDOUTS - {hs} if owner == sid else TAKEN_HOLDOUTS
    return lk.assert_lane_holdout(hs, forbidden)


def validate_lane_lock(lock: Mapping[str, Any], *, repo: Path, lock_path: Path) -> str:
    """load-time refusals: promote, book, data sha, holdout, grid cardinality.

    Returns the verified data sha256.
    """
    lk.refuse_promote_flips(lock)
    costs = lk.costs_from_lock(lock)
    lk.require_locked_book(lock, costs)
    data_rel = (lock.get("data") or {}).get("path")
    if not data_rel:
        raise SystemExit("lock missing data.path")
    data_path = Path(data_rel)
    if not data_path.is_absolute():
        data_path = repo / data_path
    want = (lock.get("data") or {}).get("sha256")
    if not want:
        raise SystemExit("lock missing data.sha256")
    data_sha = lk.verify_data_sha256(data_path, str(want))
    _assert_runner_holdout(lock)
    rows = lk.iter_product_grid(lock)
    lk.assert_cardinality(rows, lock)
    return data_sha


def resolve_runner_module(lock: Mapping[str, Any]) -> str:
    """Module name for ``run_screen``. lock['runner'] wins; else registry."""
    named = lock.get("runner")
    if named:
        return str(named)
    sid = str(lock.get("search_id") or "")
    for prefix, mod in RUNNER_REGISTRY:
        if sid == prefix or sid.startswith(prefix):
            return mod
    raise SystemExit(
        f"no runner for search_id={sid!r} (set lock['runner'] or register a prefix)"
    )


def _load_run_screen(module_name: str):
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        raise RunnerMissingError(module_name) from e
    fn = getattr(mod, "run_screen", None)
    if not callable(fn):
        raise SystemExit(f"runner {module_name} has no run_screen()")
    return fn


def verdict_row(
    *,
    search_id: str,
    disposition: str,
    lock_sha256: str,
    data_sha256: str,
    code_commit: str,
    n_eligible: int | None,
    frac_null_ge_real: float | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "search_id": search_id,
        "disposition": disposition,
        "lock_sha256": lock_sha256,
        "data_sha256": data_sha256,
        "code_commit": code_commit,
        "n_eligible": n_eligible,
        "promote": False,
    }
    if frac_null_ge_real is not None:
        row["frac_null_ge_real"] = frac_null_ge_real
    return row


def _verdict_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("search_id") or ""),
        str(row.get("lock_sha256") or ""),
        str(row.get("code_commit") or ""),
    )


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def ledger_has(path: Path, search_id: str, lock_sha256: str, code_commit: str) -> bool:
    key = (search_id, lock_sha256, code_commit)
    return any(_verdict_key(r) == key for r in _read_ledger(path))


def append_verdict(path: Path, row: Mapping[str, Any]) -> bool:
    """Append one JSONL row. Returns False if the idempotency key exists.

    Never rewrites history: read for the duplicate check, then open-append.
    """
    path = Path(path)
    if ledger_has(
        path,
        str(row.get("search_id") or ""),
        str(row.get("lock_sha256") or ""),
        str(row.get("code_commit") or ""),
    ):
        return False
    payload = dict(row)
    payload["promote"] = False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")
    return True


def stamp_digests(
    report: dict[str, Any],
    *,
    lock_sha256: str,
    data_sha256: str,
    code_commit: str,
) -> dict[str, Any]:
    """Stamp lock+data+commit into the screen JSON. Does not change metrics."""
    digests = dict(report.get("digests") or {})
    digests["lock_sha256"] = lock_sha256
    digests["data_sha256"] = data_sha256
    digests["code_commit"] = code_commit
    report["digests"] = digests
    report["promote"] = False
    return report


def _frac_null(report: Mapping[str, Any]) -> float | None:
    null = report.get("null")
    if not isinstance(null, Mapping):
        if "frac_null_ge_real" in report:
            val = report["frac_null_ge_real"]
            return None if val is None else float(val)
        return None
    val = null.get("frac_null_ge_real")
    return None if val is None else float(val)


def run_lane(lock_path: Path, out_dir: Path, *, ledger: Path | None = None) -> dict[str, Any]:
    """Validate, dispatch, stamp, append. Never simulates families itself."""
    lock_path = Path(lock_path)
    meta = require_committed_lock(lock_path)
    repo = Path(meta["repo"])
    lock = lk.load_lane_lock(lock_path)
    data_sha = validate_lane_lock(lock, repo=repo, lock_path=lock_path)
    search_id = str(lock.get("search_id") or "")
    ledger_path = Path(ledger) if ledger is not None else repo / LEDGER_NAME
    if ledger_has(ledger_path, search_id, meta["lock_sha256"], meta["code_commit"]):
        print(
            f"already recorded {search_id} lock={meta['lock_sha256'][:12]} "
            f"commit={meta['code_commit'][:12]} — skip (idempotent)"
        )
        return {
            "skipped": "duplicate",
            "search_id": search_id,
            "lock_sha256": meta["lock_sha256"],
            "code_commit": meta["code_commit"],
            "ledger": str(ledger_path),
        }
    module_name = resolve_runner_module(lock)
    try:
        run_screen = _load_run_screen(module_name)
    except RunnerMissingError as e:
        if e.module == _BNS_MODULE or module_name == _BNS_MODULE:
            msg = (
                f"skip {search_id}: {e.module} not in this tree "
                "(btc_ny_session_scalp_autoresearch.py lives on research/btc-ny-session-scalp)"
            )
            print(msg)
            return {"skipped": "runner_missing", "search_id": search_id, "module": e.module}
        raise SystemExit(f"runner module not found: {e.module}") from e

    report = run_screen(lock)
    if not isinstance(report, dict):
        raise SystemExit(f"{module_name}.run_screen did not return a dict")
    stamp_digests(
        report,
        lock_sha256=meta["lock_sha256"],
        data_sha256=data_sha,
        code_commit=meta["code_commit"],
    )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"{search_id}.json"
    lk.write_slim_json(out_json, report)

    n_eligible = report.get("n_eligible")
    row = verdict_row(
        search_id=search_id,
        disposition=str(report.get("disposition") or "UNKNOWN"),
        lock_sha256=meta["lock_sha256"],
        data_sha256=data_sha,
        code_commit=meta["code_commit"],
        n_eligible=None if n_eligible is None else int(n_eligible),
        frac_null_ge_real=_frac_null(report),
    )
    appended = append_verdict(ledger_path, row)
    if not appended:
        print(f"ledger already has {search_id} — skip append")
    else:
        print("wrote", out_json)
        print("appended", ledger_path)
    print(row["disposition"], "eligible", row["n_eligible"], "promote=false")
    return {
        "report": report,
        "verdict": row,
        "out": str(out_json),
        "ledger": str(ledger_path),
        "appended": appended,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Validate a committed lane lock, dispatch to its screen, append a verdict."
    )
    p.add_argument("--lock", type=Path, required=True, help="path to the committed lock JSON")
    p.add_argument("--out", type=Path, required=True, help="directory for the stamped screen JSON")
    p.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="JSONL ledger (default: <repo>/results/lane_verdicts.jsonl)",
    )
    args = p.parse_args(argv)
    run_lane(args.lock, args.out, ledger=args.ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
