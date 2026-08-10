#!/usr/bin/env python3
"""Immutable family charters, gate provenance, sealed-run bookkeeping.

Phase-0 research protocol (2026-08-10):

* Charters live under ``results/xau_charters/YYYY-MM-DD_<family>_vN.json``
  and are **write-once** (refuse overwrite).
* Soft/classic gates and null method/n_trials come **only** from the charter.
* Each sealed run records charter path, code commit, data SHA-256, cost-file
  SHA-256, null seed, and a unique output directory.
* Program-level family attempts are appended to
  ``results/xau_family_attempts.jsonl`` (never rewritten as a greenwash log).

Historical note: ``results/xau_next_design_charter.json`` freezes
``prior_day_high_break`` (2026-08-08). Do **not** overwrite it; new families
use the charters/ layout only.

SAFETY: offline only — no live orders.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CHARTERS_DIR = ROOT / "results" / "xau_charters"
ATTEMPTS_PATH = ROOT / "results" / "xau_family_attempts.jsonl"
LEGACY_CHARTER = ROOT / "results" / "xau_next_design_charter.json"

# Defaults when a gate field is missing (should not happen on new charters).
DEFAULT_CLASSIC_GATES = {
    "n_trades_min": 20,
    "profit_factor_min": 1.5,
    "profit_factor_strict_gt": True,
    "win_rate_min": 55.0,
    "win_rate_strict_gt": True,
    "max_drawdown_pct_max": 10.0,
    "max_drawdown_strict_lt": True,
}

# Minimum null trials for a decisive 0.05 test under add-one smoothing.
# p = (hits+1)/(n+1) ≤ 0.05 ⇒ n+1 ≥ 20 when hits=0 ⇒ n ≥ 19 is *not* enough
# resolution for reporting 0.05 cleanly; require ≥199 (p-step ≈ 0.005).
MIN_NULL_TRIALS_PROTOCOL = 199
PREFERRED_NULL_TRIALS_LOW_KNOB = 999


class CharterError(RuntimeError):
    """Invalid or conflicting charter operation."""


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(repo: Path = ROOT) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None


def charter_path(family_id: str, *, day: str | None = None, version: int = 1) -> Path:
    """``results/xau_charters/YYYY-MM-DD_<family>_vN.json``."""
    d = day or date.today().isoformat()
    safe = family_id.strip().replace(" ", "_").replace("/", "_")
    return CHARTERS_DIR / f"{d}_{safe}_v{version}.json"


def load_charter(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise CharterError(f"charter not found: {p}")
    return json.loads(p.read_text())


def write_charter_once(path: Path, charter: dict[str, Any]) -> Path:
    """Write charter JSON; refuse if the path already exists."""
    path = Path(path)
    if path.exists():
        raise CharterError(
            f"charter already exists (immutable): {path}. "
            "Bump version or change family_id/date — never overwrite."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize status
    body = dict(charter)
    body.setdefault("status", "FROZEN")
    path.write_text(json.dumps(body, indent=2, sort_keys=False) + "\n")
    return path


def validate_charter(charter: dict[str, Any]) -> list[str]:
    """Return list of hard errors (empty ⇒ ok to freeze/run)."""
    errs: list[str] = []
    if not charter.get("family_id"):
        errs.append("missing family_id")
    n_knobs = int(charter.get("n_free_knobs", len(charter.get("free_knobs") or [])))
    if n_knobs > 3:
        errs.append(f"n_free_knobs={n_knobs} > 3")
    null = charter.get("null") or charter.get("success", {}).get("null_maxstat") or {}
    n_trials = int(null.get("n_trials") or null.get("min_null_trials") or 0)
    if n_trials < MIN_NULL_TRIALS_PROTOCOL:
        errs.append(
            f"null n_trials={n_trials} < protocol floor {MIN_NULL_TRIALS_PROTOCOL} "
            f"(prefer {PREFERRED_NULL_TRIALS_LOW_KNOB} for 0–1 knob families)"
        )
    method = str(null.get("method") or null.get("null_method") or "")
    if not method:
        errs.append("null.method required (e.g. global_return_shuffle, day_block_shuffle, circular_day_shift)")
    if not (charter.get("gates") or charter.get("passer_definition_soft")):
        errs.append("gates or passer_definition_soft required")
    costs = (charter.get("fixed") or {}).get("costs") or charter.get("costs") or {}
    if "commission_per_lot" not in costs and "costs_source" not in (charter.get("fixed") or {}):
        errs.append("fixed.costs or fixed.costs_source required")
    # Intraday flat or swap handling
    rule = charter.get("rule") or {}
    exits = str(rule.get("exit") or "") + str(rule.get("intraday_flat") or "")
    if not rule.get("intraday_flat") and "swap" not in exits.lower() and "flat" not in exits.lower():
        # soft warning encoded as error for new protocol families
        if charter.get("protocol_version", 0) >= 2:
            errs.append("rule.intraday_flat true required (or explicit swap handling) under protocol v2")
    return errs


def run_output_dir(family_id: str, *, day: str | None = None, run_id: str = "r1") -> Path:
    d = day or date.today().isoformat()
    safe = family_id.strip().replace(" ", "_")
    return ROOT / "results" / "xau_runs" / f"{d}_{safe}_{run_id}"


def ensure_fresh_run_dir(path: Path) -> Path:
    if path.exists():
        raise CharterError(
            f"run output directory already exists (refuse overwrite): {path}. "
            "Choose a new run_id."
        )
    path.mkdir(parents=True, exist_ok=False)
    return path


def build_provenance(
    *,
    charter_path: Path,
    costs_path: Path,
    data_path: Path,
    null_seed: int,
    n_null: int,
    out_dir: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prov = {
        "charter_path": str(charter_path.relative_to(ROOT)) if charter_path.is_relative_to(ROOT) else str(charter_path),
        "charter_sha256": sha256_file(charter_path),
        "code_commit": git_head(),
        "data_path": str(data_path.relative_to(ROOT)) if data_path.is_relative_to(ROOT) else str(data_path),
        "data_sha256": sha256_file(data_path),
        "costs_path": str(costs_path.relative_to(ROOT)) if costs_path.is_relative_to(ROOT) else str(costs_path),
        "costs_sha256": sha256_file(costs_path),
        "null_seed": int(null_seed),
        "n_null": int(n_null),
        "output_dir": str(out_dir.relative_to(ROOT)) if out_dir.is_relative_to(ROOT) else str(out_dir),
    }
    if extra:
        prov.update(extra)
    return prov


def append_attempt(record: dict[str, Any], path: Path = ATTEMPTS_PATH) -> None:
    """Append one program-level family attempt (multiple-testing ledger)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=str)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def count_attempts(family_id: str | None = None, path: Path = ATTEMPTS_PATH) -> int:
    if not path.is_file():
        return 0
    n = 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if family_id is None or rec.get("family_id") == family_id:
            n += 1
    return n


def gates_from_charter(charter: dict[str, Any]) -> dict[str, Any]:
    """Normalize classic + soft gate specs for reporting and evaluation."""
    g = dict(charter.get("gates") or {})
    classic = dict(DEFAULT_CLASSIC_GATES)
    classic.update(g.get("classic") or {})

    soft = g.get("soft")
    if soft is None and charter.get("passer_definition_soft"):
        p = charter["passer_definition_soft"]
        soft = {
            "n_trades_min": p.get("n_trades_min", 20),
            "profit_factor_min": p.get("profit_factor_min", 1.2),
            "net_profit_gt": 0.0 if p.get("net_profit") in ("gt_0", ">", 0) else p.get("net_profit_gt"),
            "max_drawdown_pct_max": p.get("max_drawdown_pct_max"),
            "expectancy_min": p.get("expectancy_min"),
            "used_for": p.get("used_for", "null_n_passers"),
        }
    soft = dict(soft or {})

    primary = g.get("primary_n_passers") or charter.get("primary_n_passers") or "soft"
    return {
        "classic": classic,
        "soft": soft,
        "primary_n_passers": primary,
        "description": {
            "classic": _gate_desc(classic, kind="classic"),
            "soft": _gate_desc(soft, kind="soft") if soft else None,
        },
    }


def _gate_desc(g: dict[str, Any], *, kind: str) -> str:
    parts: list[str] = []
    if "n_trades_min" in g:
        parts.append(f"n>={g['n_trades_min']}")
    if "profit_factor_min" in g:
        op = ">" if g.get("profit_factor_strict_gt") else ">="
        parts.append(f"PF{op}{g['profit_factor_min']}")
    if "win_rate_min" in g:
        op = ">" if g.get("win_rate_strict_gt") else ">="
        parts.append(f"WR{op}{g['win_rate_min']}")
    if g.get("max_drawdown_pct_max") is not None:
        op = "<" if g.get("max_drawdown_strict_lt") else "<="
        parts.append(f"DD{op}{g['max_drawdown_pct_max']}")
    if g.get("expectancy_min") is not None:
        parts.append(f"exp>={g['expectancy_min']}")
    if g.get("net_profit_gt") is not None:
        parts.append(f"NP>{g['net_profit_gt']}")
    return ", ".join(parts) if parts else kind


def make_pass_fns(charter: dict[str, Any]) -> tuple[Callable[[Any], bool], Callable[[Any], bool] | None, str]:
    """Build classic/soft pass callables from charter gates (not from module drift)."""
    from xau_null_core import metrics_dict  # local import; scripts on path

    g = gates_from_charter(charter)
    classic_spec = g["classic"]
    soft_spec = g["soft"]

    def classic_pass(m: Any) -> bool:
        md = metrics_dict(m) if not isinstance(m, dict) else m
        pf = float(md["profit_factor"])
        wr = float(md["win_rate"])
        dd = float(md["max_drawdown_pct"])
        n = int(md["n_trades"])
        if n < int(classic_spec.get("n_trades_min", 20)):
            return False
        pf_min = float(classic_spec.get("profit_factor_min", 1.5))
        if classic_spec.get("profit_factor_strict_gt", True):
            if not (pf > pf_min):
                return False
        elif not (pf >= pf_min):
            return False
        wr_min = float(classic_spec.get("win_rate_min", 55.0))
        if classic_spec.get("win_rate_strict_gt", True):
            if not (wr > wr_min):
                return False
        elif not (wr >= wr_min):
            return False
        dd_max = float(classic_spec.get("max_drawdown_pct_max", 10.0))
        if classic_spec.get("max_drawdown_strict_lt", True):
            if not (dd < dd_max):
                return False
        elif not (dd <= dd_max):
            return False
        return True

    soft_fn: Callable[[Any], bool] | None = None
    if soft_spec:

        def _soft(m: Any) -> bool:
            md = metrics_dict(m) if not isinstance(m, dict) else m
            if int(md["n_trades"]) < int(soft_spec.get("n_trades_min", 0) or 0):
                return False
            if "profit_factor_min" in soft_spec and float(md["profit_factor"]) < float(
                soft_spec["profit_factor_min"]
            ):
                return False
            if soft_spec.get("net_profit_gt") is not None and not (
                float(md["net_profit"]) > float(soft_spec["net_profit_gt"])
            ):
                return False
            if soft_spec.get("max_drawdown_pct_max") is not None and float(
                md["max_drawdown_pct"]
            ) > float(soft_spec["max_drawdown_pct_max"]):
                return False
            if soft_spec.get("expectancy_min") is not None and float(md["expectancy"]) < float(
                soft_spec["expectancy_min"]
            ):
                return False
            return True

        soft_fn = _soft

    primary = str(g["primary_n_passers"])
    return classic_pass, soft_fn, primary


def null_spec_from_charter(charter: dict[str, Any]) -> dict[str, Any]:
    null = dict(charter.get("null") or {})
    legacy = (charter.get("success") or {}).get("null_maxstat") or {}
    for k, v in legacy.items():
        null.setdefault(k, v)
    method = str(null.get("method") or null.get("null_method") or "global_return_shuffle")
    n_trials = int(null.get("n_trials") or null.get("min_null_trials") or MIN_NULL_TRIALS_PROTOCOL)
    block_days = int(null.get("block_days") or null.get("block_size_days") or 1)
    return {
        "method": method,
        "n_trials": n_trials,
        "block_days": block_days,
        "invariants": null.get("invariants") or [],
        "notes": null.get("notes") or "",
    }


if __name__ == "__main__":
    print(f"CHARTERS_DIR={CHARTERS_DIR}")
    print(f"LEGACY_CHARTER exists={LEGACY_CHARTER.is_file()}")
    print(f"attempts={count_attempts()}")
