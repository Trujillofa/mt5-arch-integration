#!/usr/bin/env python3
"""Reusable null / max-stat harness for any XAU strategy family.

Question: does best-of-grid on real develop bars sit outside the distribution of
best-of-grid on return-shuffled bars (no predictive structure)?

If not, the gates measured the search, not the market — KILL the family rather
than tune it further.

Protocol
--------
* Window: develop only (``time < holdout_start``). Holdout stays sealed.
* Costs: ``load_research_costs()`` (Vantage RAW floor / research JSON).
* Null: ``scramble_ohlc`` return-shuffle; re-prepare; re-score full grid.
* Max-stat gated on ``n_trades >= 20`` so the PF=99 thin-sample cap cannot dominate.
* Gates: classic ``passes`` always; optional soft (family or turtle expectancy).
* Decision: KILL if ``p_max_pf > 0.05`` OR ``p_n_passers > 0.05``.

Plugin API (family module or built-in)
--------------------------------------
Required:
  * ``grid(*, max_n: int, seed: int) -> list[dict]``
  * ``simulate(d, **params) -> Metrics``  (accepts cost kwargs)

Optional:
  * ``prepare(raw) -> DataFrame``  (default: identity / passthrough)
  * ``classic_pass(m) -> bool``     (default: backtest.passes / hard classic)
  * ``soft_pass(m) -> bool``        (if set, primary n_passers uses soft)
  * ``use_soft_primary: bool``      (default True when soft_pass is provided)
  * ``FAMILY`` / ``NAME`` str
  * ``kill_label: str``             (default KILL_{FAMILY}_LINE)

Built-ins: ``stub`` (cheap smoke family; no full bar walk).

CLI
---
  python3 scripts/xau_family_null_maxstat.py --family stub --quick
  python3 scripts/xau_family_null_maxstat.py --family NAME --n-null 40 --max-n 1200

Writes:
  results/xau_{family}_null_maxstat.json
  results/xau_{family}_null_maxstat.md

SAFETY: offline only — no live orders, no holdout selection.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from xau_charter_protocol import (  # noqa: E402, I001
    MIN_NULL_TRIALS_PROTOCOL,
    CharterError,
    assert_charter_path_for_sealed,
    assert_clean_dispositional_tree,
    build_provenance,
    gates_from_charter,
    is_charter_runnable,
    load_charter,
    make_pass_fns,
    null_spec_from_charter,
    validate_charter,
)
from xau_null_core import (  # noqa: E402, I001
    MIN_TRADES_MAX_STAT,
    apply_null_method,
    dist_summary,
    hard_pass_classic,
    metrics_dict,
    pvalue,
    serializable_params,
    soft_pass_expectancy,
    subsample_grid,
)
from xau_research_costs import RESEARCH_COSTS_PATH, load_research_costs  # noqa: E402, I001

from backtest import (  # noqa: E402, I001
    CSV_PATH,
    Metrics,
    develop_only,
    holdout_start,
    load_h1,
    passes as backtest_passes,
)

# Account-matched research costs (Standard STP: commission 0 + measured spread).
# Slippage still unmeasured (0); not "fully live-matched".
COSTS: dict[str, Any] = load_research_costs()

# Worker globals (fork COW on Linux; re-init on spawn).
_W: dict[str, Any] = {}

SimulateFn = Callable[..., Metrics]
PrepareFn = Callable[[pd.DataFrame], pd.DataFrame]
PassFn = Callable[[Any], bool]


@dataclass
class FamilyPlugin:
    name: str
    grid: Callable[..., list[dict]]
    simulate: SimulateFn
    prepare: PrepareFn
    classic_pass: PassFn
    soft_pass: PassFn | None
    use_soft_primary: bool
    kill_label: str
    source: str


# ---------------------------------------------------------------------------
# Built-in stub family (smoke only)
# ---------------------------------------------------------------------------
def _stub_prepare(raw: pd.DataFrame) -> pd.DataFrame:
    return raw


def _stub_grid(*, max_n: int = 1200, seed: int = 42) -> list[dict]:
    """Tiny deterministic grid — cheap smoke, not a real family."""
    full = [{"k": k, "bias": b} for k in (1, 2, 3, 5, 8) for b in (-1.0, 0.0, 1.0)]
    return subsample_grid(full, max_n=max_n, seed=seed)


def _stub_simulate(d: pd.DataFrame, **params: Any) -> Metrics:
    """O(n) toy sim: sign of mean log-return * k + bias → synthetic trades.

    Sensitive to path structure so return-shuffle nulls move the max-stat, but
    cheap enough that ``--quick`` finishes in seconds.
    """
    k = float(params.get("k", 1))
    bias = float(params.get("bias", 0.0))
    c = d["close"].to_numpy(dtype=float)
    if len(c) < 50:
        return Metrics(0.0, 0.0, 0.0, 0.0, 0, 0, 0)
    rets = np.diff(np.log(np.clip(c, 1e-12, None)))
    # non-overlapping blocks → pseudo-trades
    block = max(20, int(40 / max(k, 1.0)))
    pnls: list[float] = []
    for i in range(0, len(rets) - block, block):
        chunk = rets[i : i + block]
        signal = float(np.mean(chunk[: block // 2])) * k + bias * 1e-4
        if abs(signal) < 1e-8:
            continue
        direction = 1.0 if signal > 0 else -1.0
        # forward half of block
        fwd = float(np.sum(chunk[block // 2 :]))
        # cost drag (uses commission kwargs if present for path coverage)
        cost = float(params.get("commission_per_lot", 0.0) or 0.0) * 0.01
        pnl = direction * fwd * 10_000.0 - cost
        pnls.append(pnl)
    if not pnls:
        return Metrics(0.0, 0.0, 0.0, 0.0, 0, 0, 0)
    arr = np.asarray(pnls, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gp = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = (gp / gl) if gl > 1e-12 else (99.0 if gp > 0 else 0.0)
    wr = 100.0 * float(len(wins)) / float(len(arr))
    # crude equity DD
    eq = np.cumsum(arr)
    peak = np.maximum.accumulate(eq)
    dd = float(np.max(peak - eq)) if len(eq) else 0.0
    start = 10_000.0
    dd_pct = 100.0 * dd / max(start, 1.0)
    return Metrics(
        net_profit=float(arr.sum()),
        win_rate=wr,
        profit_factor=min(pf, 99.0),
        max_drawdown_pct=dd_pct,
        n_trades=int(len(arr)),
        wins=int(len(wins)),
        losses=int(len(losses)),
    )


def _builtin_stub() -> FamilyPlugin:
    return FamilyPlugin(
        name="stub",
        grid=_stub_grid,
        simulate=_stub_simulate,
        prepare=_stub_prepare,
        classic_pass=lambda m: hard_pass_classic(metrics_dict(m)),
        soft_pass=lambda m: soft_pass_expectancy(metrics_dict(m)),
        use_soft_primary=True,
        kill_label="KILL_STUB_LINE",
        source="builtin:stub",
    )


def _builtin_prior_day_high_break() -> FamilyPlugin:
    """Charter family: prior_day_high_break (results/xau_next_design_charter.json)."""
    import xau_family_prior_day_high_break as mod

    return _wrap_module("prior_day_high_break", mod, source="builtin:prior_day_high_break")


def _builtin_tod_london_ny_flat() -> FamilyPlugin:
    import xau_family_tod_london_ny_flat as mod  # type: ignore

    return _wrap_module("tod_london_ny_flat", mod, source="xau_family_tod_london_ny_flat")


def _builtin_server_hour_window_flat() -> FamilyPlugin:
    import xau_family_server_hour_window_flat as mod  # type: ignore

    return _wrap_module(
        "server_hour_window_flat", mod, source="xau_family_server_hour_window_flat"
    )


BUILTINS: dict[str, Callable[[], FamilyPlugin]] = {
    "stub": _builtin_stub,
    "prior_day_high_break": _builtin_prior_day_high_break,
    "tod_london_ny_flat": _builtin_tod_london_ny_flat,
    "server_hour_window_flat": _builtin_server_hour_window_flat,
}


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------
def _identity_prepare(raw: pd.DataFrame) -> pd.DataFrame:
    return raw


def _default_classic(m: Any) -> bool:
    try:
        return bool(backtest_passes(m))
    except Exception:
        return hard_pass_classic(metrics_dict(m))


def _wrap_module(name: str, mod: ModuleType, source: str) -> FamilyPlugin:
    if not hasattr(mod, "grid") or not hasattr(mod, "simulate"):
        raise SystemExit(
            f"Family module {source!r} must provide grid(*, max_n, seed) and simulate(d, **params)"
        )
    prepare = getattr(mod, "prepare", None) or getattr(mod, "prepare_frame", None)
    if prepare is None:
        prepare = _identity_prepare
    classic = getattr(mod, "classic_pass", None)
    if classic is None:
        classic = _default_classic
    soft = getattr(mod, "soft_pass", None)
    # optional: soft_pass_expectancy flag
    if soft is None and bool(getattr(mod, "use_soft_expectancy", False)):
        soft = lambda m: soft_pass_expectancy(metrics_dict(m))  # noqa: E731
    use_soft = bool(getattr(mod, "use_soft_primary", soft is not None))
    fam_name = str(getattr(mod, "FAMILY", None) or getattr(mod, "NAME", None) or name)
    kill = str(getattr(mod, "kill_label", None) or f"KILL_{fam_name.upper()}_LINE")
    return FamilyPlugin(
        name=fam_name,
        grid=mod.grid,
        simulate=mod.simulate,
        prepare=prepare,
        classic_pass=classic,
        soft_pass=soft,
        use_soft_primary=use_soft and soft is not None,
        kill_label=kill,
        source=source,
    )


def load_family(name: str) -> FamilyPlugin:
    """Resolve ``--family`` to a plugin: built-in, module path, or xau_family_*."""
    key = name.strip()
    if not key:
        raise SystemExit("--family is required")

    low = key.lower().replace("-", "_")
    if low in BUILTINS:
        return BUILTINS[low]()

    # Path to a .py file
    path = Path(key)
    if path.suffix == ".py" and path.is_file():
        import importlib.util as _ilu

        spec = _ilu.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            raise SystemExit(f"Cannot load family from {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = mod
        spec.loader.exec_module(mod)
        return _wrap_module(path.stem, mod, source=str(path))

    # Module import candidates (scripts/ on sys.path)
    candidates = [
        key,
        low,
        f"xau_family_{low}",
        f"xau_families.{low}",
        f"xau_families_{low}",
    ]
    # strip common prefixes if user passed xau_family_foo already
    if low.startswith("xau_family_"):
        candidates.append(low)

    errors: list[str] = []
    for mod_name in candidates:
        try:
            mod = importlib.import_module(mod_name)
            return _wrap_module(low, mod, source=mod_name)
        except ModuleNotFoundError as e:
            errors.append(f"{mod_name}: {e}")
            continue
        except SystemExit:
            raise
        except Exception as e:
            errors.append(f"{mod_name}: {type(e).__name__}: {e}")
            continue

    raise SystemExit(
        f"Unknown family {name!r}. Built-ins: {sorted(BUILTINS)}. "
        f"Tried imports: {candidates}. Errors: {errors[:5]}"
    )


# ---------------------------------------------------------------------------
# Grid scoring
# ---------------------------------------------------------------------------
def score_grid(
    d: pd.DataFrame,
    candidates: list[dict],
    *,
    simulate_fn: SimulateFn,
    classic_pass_fn: PassFn,
    soft_pass_fn: PassFn | None,
    costs: dict[str, Any],
    progress_every: int = 0,
    label: str = "",
    min_trades: int = MIN_TRADES_MAX_STAT,
) -> dict[str, Any]:
    """Score every candidate (no early exit). Max-stat gated on n_trades."""
    n = len(candidates)
    pfs = np.empty(n, dtype=float)
    nets = np.empty(n, dtype=float)
    wrs = np.empty(n, dtype=float)
    dds = np.empty(n, dtype=float)
    ntr = np.empty(n, dtype=int)
    exps = np.empty(n, dtype=float)
    classic_mask = np.zeros(n, dtype=bool)
    soft_mask = np.zeros(n, dtype=bool)

    best_pf_i = 0
    best_pf = -1.0
    best_min_pf_i = -1
    best_min_pf = -1.0
    best_soft_i = -1
    best_soft_exp = -1e18

    t0 = time.time()
    for i, p in enumerate(candidates):
        m = simulate_fn(d, **{**costs, **p})
        md = metrics_dict(m)
        pfs[i] = float(md["profit_factor"])
        nets[i] = float(md["net_profit"])
        wrs[i] = float(md["win_rate"])
        dds[i] = float(md["max_drawdown_pct"])
        ntr[i] = int(md["n_trades"])
        exps[i] = float(md["expectancy"])
        classic_mask[i] = bool(classic_pass_fn(m))
        soft_mask[i] = bool(soft_pass_fn(m)) if soft_pass_fn is not None else False

        if pfs[i] > best_pf or (pfs[i] == best_pf and nets[i] > nets[best_pf_i]):
            best_pf = float(pfs[i])
            best_pf_i = i
        if ntr[i] >= min_trades and (
            pfs[i] > best_min_pf
            or (
                pfs[i] == best_min_pf
                and best_min_pf_i >= 0
                and nets[i] > nets[best_min_pf_i]
            )
        ):
            best_min_pf = float(pfs[i])
            best_min_pf_i = i
        if soft_mask[i] and (
            exps[i] > best_soft_exp
            or (exps[i] == best_soft_exp and pfs[i] > pfs[max(best_soft_i, 0)])
        ):
            best_soft_exp = exps[i]
            best_soft_i = i

        if progress_every and (i + 1) % progress_every == 0:
            print(
                f"  [{label}] {i + 1}/{n} "
                f"best_PF@>={min_trades}={best_min_pf:.3f} "
                f"classic={int(classic_mask[: i + 1].sum())} "
                f"soft={int(soft_mask[: i + 1].sum())} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    def _row(i: int) -> dict:
        return {
            "index": int(i),
            "params": serializable_params(candidates[i]),
            "profit_factor": float(pfs[i]),
            "net_profit": float(nets[i]),
            "win_rate": float(wrs[i]),
            "max_drawdown_pct": float(dds[i]),
            "n_trades": int(ntr[i]),
            "expectancy": float(exps[i]),
            "passes_classic": bool(classic_mask[i]),
            "passes_soft": bool(soft_mask[i]),
        }

    eligible = ntr >= min_trades
    max_pf_min = float(pfs[eligible].max()) if eligible.any() else 0.0
    max_net_min = float(nets[eligible].max()) if eligible.any() else 0.0
    top_min_idx = np.argsort(-np.where(eligible, pfs, -1e18))[:20]

    n_classic = int(classic_mask.sum())
    n_soft = int(soft_mask.sum()) if soft_pass_fn is not None else 0

    return {
        "n_configs": n,
        "min_trades_gate": min_trades,
        "elapsed_s": float(time.time() - t0),
        "best_by_pf": _row(best_pf_i),
        "best_by_pf_min_trades": _row(best_min_pf_i) if best_min_pf_i >= 0 else None,
        "best_soft_passer": _row(best_soft_i) if best_soft_i >= 0 else None,
        "n_passers_classic": n_classic,
        "n_passers_soft": n_soft,
        "n_with_min_trades": int(eligible.sum()),
        "pf": {
            "max_raw": float(pfs.max()) if n else 0.0,
            "max_min_trades": max_pf_min,
            "p50": float(np.median(pfs)) if n else 0.0,
            "p90": float(np.quantile(pfs, 0.90)) if n else 0.0,
            "p99": float(np.quantile(pfs, 0.99)) if n else 0.0,
            "mean": float(pfs.mean()) if n else 0.0,
        },
        "net_profit": {
            "max_raw": float(nets.max()) if n else 0.0,
            "max_min_trades": max_net_min,
            "p50": float(np.median(nets)) if n else 0.0,
            "mean": float(nets.mean()) if n else 0.0,
        },
        "top20_by_pf_min_trades": [
            _row(int(i)) for i in top_min_idx if eligible[int(i)]
        ],
        "max_pf": max_pf_min,
        "max_net": max_net_min,
        "max_pf_raw": float(pfs.max()) if n else 0.0,
    }


# ---------------------------------------------------------------------------
# Parallel null workers
# ---------------------------------------------------------------------------
def _init_worker(
    raw_records: list,
    candidates: list[dict],
    costs: dict,
    family_name: str,
    null_method: str = "global_return_shuffle",
    block_days: int = 1,
    charter_path: str | None = None,
) -> None:
    global COSTS
    COSTS = dict(costs)
    # ensure import path in spawn workers
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    plugin = load_family(family_name)
    # Charter gates override module soft/classic passers when provided.
    if charter_path:
        ch = load_charter(charter_path)
        classic_fn, soft_fn, primary = make_pass_fns(ch)
        plugin.classic_pass = classic_fn
        plugin.soft_pass = soft_fn
        plugin.use_soft_primary = primary == "soft" and soft_fn is not None
    raw = pd.DataFrame.from_records(raw_records)
    raw["time"] = pd.to_datetime(raw["time"], utc=True)
    _W["raw"] = raw
    _W["candidates"] = candidates
    _W["costs"] = COSTS
    _W["plugin"] = plugin
    _W["null_method"] = null_method
    _W["block_days"] = int(block_days)


def _null_trial(trial: int, base_seed: int) -> dict[str, Any]:
    raw = _W["raw"]
    candidates = _W["candidates"]
    costs = _W["costs"]
    plugin: FamilyPlugin = _W["plugin"]
    method = str(_W.get("null_method") or "global_return_shuffle")
    block_days = int(_W.get("block_days") or 1)
    rng = np.random.default_rng(base_seed + trial * 1_000_003)
    scr = apply_null_method(raw, rng, method=method, block_days=block_days)
    d = plugin.prepare(scr)
    summary = score_grid(
        d,
        candidates,
        simulate_fn=plugin.simulate,
        classic_pass_fn=plugin.classic_pass,
        soft_pass_fn=plugin.soft_pass,
        costs=costs,
        progress_every=0,
        label=f"null{trial}",
    )
    n_passers_primary = (
        summary["n_passers_soft"]
        if plugin.use_soft_primary
        else summary["n_passers_classic"]
    )
    return {
        "trial": trial,
        "seed": int(base_seed + trial * 1_000_003),
        "max_pf": summary["max_pf"],
        "max_net": summary["max_net"],
        "n_passers": int(n_passers_primary),
        "n_passers_soft": summary["n_passers_soft"],
        "n_passers_classic": summary["n_passers_classic"],
        "best_by_pf_min_trades": summary["best_by_pf_min_trades"],
        "elapsed_s": summary["elapsed_s"],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def write_markdown(report: dict, path: Path) -> None:
    real = report["real"]
    null = report["null"]
    verdict = report["verdict"]
    fam = report["family"]
    primary = report["gates"]["primary_n_passers"]
    lines = [
        f"# XAU family null / max-stat — `{fam}`",
        "",
        f"**Disposition:** `{verdict['disposition']}`",
        "",
        verdict["reason"],
        "",
        "## Protocol",
        "",
        f"- Family: `{fam}` (source={report['family_source']})",
        f"- Window: develop only (`time < {report['window']['holdout_start']}`), "
        f"{report['window']['bars']} H1 bars "
        f"({report['window']['start']} → {report['window']['end']})",
        f"- Grid: {report['grid']['n_configs']} configs "
        f"(max_n={report['grid']['max_n']}, seed={report['grid']['seed']}) — no early exit",
        f"- Null planned/executed: "
        f"{null.get('n_null_planned', null.get('n_trials'))}/"
        f"{null.get('n_null_executed', null.get('n_trials'))} "
        f"(method=`{null.get('method', '?')}`)",
        f"- Costs: `{json.dumps(report['costs'])}` "
        f"(slippage may be 0/unmeasured — not fully live-matched)",
        f"- Classic gates (from charter if provided): {report['gates']['classic']}",
        f"- Soft gates (from charter if provided): {report['gates'].get('soft') or 'n/a'}",
        f"- Primary n_passers: **{primary}**",
        f"- Max-stat min trades: {report['gates']['max_pf_min_trades']}",
        f"- Charter: {report.get('charter_path') or 'none (legacy module gates)'}",
        f"- Attempt type: `{ (report.get('attempt_accounting') or {}).get('attempt_type') }`",
        "",
        "## Real grid (develop, costed)",
        "",
        "Max-stat is gated on `n_trades >= 20` so the PF=99 thin-sample cap cannot dominate.",
        "",
        "| Stat | Value |",
        "|---|---|",
        f"| max PF (n≥20) | {real['max_pf']:.4f} |",
        f"| max net (n≥20) | ${real['max_net']:.2f} |",
        f"| max PF raw (incl. thin) | {real.get('max_pf_raw', real['max_pf']):.4f} |",
        f"| n_passers (primary={primary}) | {real['n_passers']} |",
        f"| n_passers_classic | {real['n_passers_classic']} |",
        f"| n_passers_soft | {real['n_passers_soft']} |",
        f"| n with ≥20 trades | {real.get('n_with_min_trades', '?')} |",
        f"| PF p50 / p90 / p99 | {real['pf']['p50']:.3f} / {real['pf']['p90']:.3f} / {real['pf']['p99']:.3f} |",
        f"| elapsed | {real['elapsed_s']:.0f}s |",
        "",
        "Best by PF among n≥20:",
        "",
        "```json",
        json.dumps(real.get("best_by_pf_min_trades") or real["best_by_pf"], indent=2),
        "```",
        "",
    ]
    if null.get("skipped_reason"):
        lines += [
            "## Null distribution",
            "",
            f"**Skipped:** `{null.get('skipped_reason')}` "
            f"(planned={null.get('n_null_planned')}, executed={null.get('n_null_executed')}).",
            "",
            f"- p_n_passers: **{null.get('p_n_passers')}** "
            f"({null.get('p_n_passers_status')})",
            f"- p_max_pf: **{null.get('p_max_pf')}** ({null.get('p_max_pf_status')})",
            "",
        ]
    else:
        nmp = null.get("max_pf") or {}
        nnp = null.get("n_passers") or {}
        nnc = null.get("n_passers_classic") or {}
        lines += [
            "## Null distribution (best-of-grid per trial, n≥20 gated PF)",
            "",
            "| Stat | null max | null p50 | null p90 | p(null ≥ real) |",
            "|---|---|---|---|---|",
            f"| max PF (n≥20) | {nmp.get('max', float('nan')):.4f} | "
            f"{nmp.get('p50', float('nan')):.4f} | "
            f"{nmp.get('p90', float('nan')):.4f} | **{null.get('p_max_pf')}** |",
            f"| n_passers (primary) | {nnp.get('max', float('nan'))} | "
            f"{nnp.get('p50', float('nan')):.1f} | "
            f"{nnp.get('p90', float('nan')):.1f} | **{null.get('p_n_passers')}** |",
            f"| n_passers_classic | {nnc.get('max', float('nan'))} | "
            f"{nnc.get('p50', float('nan')):.1f} | "
            f"{nnc.get('p90', float('nan')):.1f} | "
            f"**{null.get('p_n_passers_classic')}** |",
            "",
        ]
    lines += [
        "## Decision rule",
        "",
        f"- Fail (`{report['kill_label']}`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05` —",
        "  real best-of-grid is typical of noise under the same search.",
        "- **SCREEN_FAIL** if real primary passers=0 (null not run; p_n_passers implied 1.0).",
        "- Weak if only one of the two fails; still no promote.",
        "- Pass only if both p-values ≤ 0.05 **and** real n_passers > null p90 — still not",
        "  a live go; only permission to keep researching the family.",
        "",
        f"Elapsed total: {report['elapsed_s']:.0f}s",
        "",
        f"promote=no | live_go=false | quick={report.get('quick', False)}",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def out_paths(family: str) -> tuple[Path, Path]:
    safe = family.lower().replace("-", "_").replace("/", "_").replace(".", "_")
    # strip common prefixes for cleaner artifact names
    for prefix in ("xau_family_", "xau_families_"):
        if safe.startswith(prefix):
            safe = safe[len(prefix) :]
    base = ROOT / "results" / f"xau_{safe}_null_maxstat"
    return base.with_suffix(".json"), base.with_suffix(".md")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--family",
        required=True,
        help="family name (builtin: stub) or module providing grid()+simulate()",
    )
    ap.add_argument(
        "--charter",
        default=None,
        help="immutable charter JSON path (gates + null method/n_trials; required for protocol runs)",
    )
    ap.add_argument(
        "--out-dir",
        default=None,
        help="write JSON/MD into this directory (refuse if files exist)",
    )
    ap.add_argument(
        "--n-null",
        type=int,
        default=None,
        help=f"null trials (default from charter or {MIN_NULL_TRIALS_PROTOCOL}; protocol floor {MIN_NULL_TRIALS_PROTOCOL})",
    )
    ap.add_argument(
        "--null-method",
        default=None,
        help="override null method (default from charter or global_return_shuffle)",
    )
    ap.add_argument("--max-n", type=int, default=1200, help="grid subsample size")
    ap.add_argument(
        "--allow-low-n-null",
        action="store_true",
        help="allow n_null below protocol floor (smoke/quick only; not for disposition)",
    )
    ap.add_argument(
        "--strict-charter",
        action="store_true",
        help="require --charter; refuse family/null/cost mismatches; no CLI null overrides",
    )
    ap.add_argument(
        "--allow-charter-override",
        action="store_true",
        help="allow CLI --n-null/--null-method to differ from charter (marks non-dispositional)",
    )
    ap.add_argument("--seed", type=int, default=42, help="grid subsample seed")
    ap.add_argument("--null-seed", type=int, default=20260808, help="base seed for nulls")
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 2) - 1)),
        help="parallel null workers (default min(8, ncpu-1))",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="smoke: max_n=40, n_null=4 (not for disposition)",
    )
    ap.add_argument("--progress-every", type=int, default=200)
    ap.add_argument(
        "--no-soft-primary",
        action="store_true",
        help="force primary n_passers = classic even if family defines soft_pass",
    )
    args = ap.parse_args(argv)

    charter: dict[str, Any] | None = None
    charter_path: Path | None = None
    null_method = "global_return_shuffle"
    block_days = 1
    gate_desc_classic = "n>=20, PF>1.5, WR>55, DD<10"
    gate_desc_soft: str | None = "PF>=1.5, n>=40, DD<=12, expectancy>=20"
    non_dispositional = False
    slip_sensitivity_pts: list[float] = []

    if args.strict_charter and not args.charter:
        raise SystemExit("--strict-charter requires --charter")

    cli_n_null = args.n_null  # None unless user passed --n-null
    cli_null_method = args.null_method

    if args.charter:
        charter_path = Path(args.charter)
        ok_run, why = is_charter_runnable(charter_path)
        if not ok_run:
            raise SystemExit(f"charter not runnable: {why}")
        if args.strict_charter and not args.quick:
            try:
                assert_charter_path_for_sealed(charter_path)
            except CharterError as e:
                raise SystemExit(str(e)) from e
        charter = load_charter(charter_path)
        # Same enforcement as sealed cycle: full charter validation
        verrs = validate_charter(charter)
        if verrs:
            if args.quick and not args.strict_charter:
                print("WARNING charter validation:", verrs, flush=True)
            else:
                raise SystemExit("charter validation failed:\n- " + "\n- ".join(verrs))
        if args.strict_charter and not args.quick:
            try:
                assert_clean_dispositional_tree()
            except CharterError as e:
                raise SystemExit(str(e)) from e
        ns = null_spec_from_charter(charter)
        charter_n_null = int(ns["n_trials"])
        charter_method = str(ns["method"])
        block_days = int(ns["block_days"])
        null_method = charter_method
        args.n_null = charter_n_null if cli_n_null is None else int(cli_n_null)
        gmeta = gates_from_charter(charter)
        gate_desc_classic = gmeta["description"]["classic"]
        gate_desc_soft = gmeta["description"]["soft"]
        # family id must match charter
        fid = str(charter.get("family_id") or "")
        cli = args.family.strip().replace("-", "_")
        if cli.startswith("xau_family_"):
            cli = cli[len("xau_family_") :]
        if cli != fid:
            if args.strict_charter:
                raise SystemExit(
                    f"family mismatch: --family={args.family!r} "
                    f"charter.family_id={fid!r}"
                )
            print(
                f"WARNING: --family={args.family!r} != charter.family_id={fid!r}",
                flush=True,
            )
            non_dispositional = True
        # costs equality: every sim key in charter.fixed.costs must exist and match
        fixed_costs = (charter.get("fixed") or {}).get("costs") or {}
        for k in ("spread_col", "point_size", "commission_per_lot", "slippage_points"):
            if k not in fixed_costs:
                continue
            if k not in COSTS:
                raise SystemExit(
                    f"cost key {k!r} present in charter but absent from loaded costs"
                )
            a, b = fixed_costs[k], COSTS[k]
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(float(a) - float(b)) > 1e-12:
                    raise SystemExit(f"cost mismatch {k}: charter={a} loaded={b}")
            elif a != b:
                raise SystemExit(f"cost mismatch {k}: charter={a!r} loaded={b!r}")
        # CLI overrides vs charter
        if cli_null_method and str(cli_null_method) != charter_method:
            if args.strict_charter and not args.allow_charter_override:
                raise SystemExit(
                    f"--null-method={cli_null_method!r} != charter {charter_method!r}"
                )
            null_method = str(cli_null_method)
            non_dispositional = True
        if cli_n_null is not None and int(cli_n_null) != charter_n_null:
            if args.quick:
                pass
            elif args.strict_charter and not args.allow_charter_override:
                raise SystemExit(
                    f"--n-null={cli_n_null} != charter n_trials={charter_n_null}"
                )
            else:
                non_dispositional = True
        slip_sensitivity_pts = list(
            (charter.get("success") or {})
            .get("slippage_sensitivity", {})
            .get("points")
            or []
        )

    if args.n_null is None:
        args.n_null = MIN_NULL_TRIALS_PROTOCOL
    if args.null_method and not args.charter:
        null_method = str(args.null_method)

    if args.quick:
        args.max_n = min(args.max_n, 40)
        args.n_null = min(int(args.n_null), 4)
        args.allow_low_n_null = True
        non_dispositional = True
        print(
            f"QUICK smoke mode: max_n={args.max_n} n_null={args.n_null} — "
            "do not use for disposition",
            flush=True,
        )

    if int(args.n_null) < MIN_NULL_TRIALS_PROTOCOL and not args.allow_low_n_null:
        raise SystemExit(
            f"n_null={args.n_null} < protocol floor {MIN_NULL_TRIALS_PROTOCOL}. "
            "Pass --allow-low-n-null only for smoke, or raise n_trials in the charter."
        )

    args.workers = max(1, min(8, int(args.workers)))

    plugin = load_family(args.family)
    if charter is not None:
        classic_fn, soft_fn, primary = make_pass_fns(charter)
        plugin.classic_pass = classic_fn
        plugin.soft_pass = soft_fn
        plugin.use_soft_primary = primary == "soft" and soft_fn is not None
        if charter.get("kill", {}).get("on_null_fail"):
            plugin.kill_label = str(charter["kill"]["on_null_fail"])
    if args.no_soft_primary:
        plugin.use_soft_primary = False

    family_key = plugin.name
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir = (ROOT / out_dir).resolve() if not out_dir.is_absolute() else out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_json = out_dir / "null_maxstat.json"
        out_md = out_dir / "null_maxstat.md"
    else:
        out_json, out_md = out_paths(family_key)
    if out_json.exists() or out_md.exists():
        raise SystemExit(
            f"refuse overwrite of existing results: {out_json} / {out_md}. "
            "Use a fresh --out-dir or remove artifacts deliberately."
        )

    t_all = time.time()
    cutoff = holdout_start()
    if cutoff is None:
        raise SystemExit("results/xau_holdout_lock.json missing holdout_start — refuse to run")

    raw_full = load_h1()
    raw = develop_only(raw_full, cutoff)
    print(
        f"Family: {plugin.name} ({plugin.source})",
        flush=True,
    )
    print(
        f"Develop window: {len(raw)} H1 bars  {raw['time'].iloc[0]} → {raw['time'].iloc[-1]}",
        flush=True,
    )
    print(f"Costs: {COSTS} (slippage may be unmeasured)", flush=True)
    print(f"Null method: {null_method} block_days={block_days} n_null={args.n_null}", flush=True)
    if charter_path:
        print(f"Charter: {charter_path}", flush=True)

    # Build grid — family may already subsample; we enforce max_n after if needed
    try:
        candidates = plugin.grid(max_n=args.max_n, seed=args.seed)
    except TypeError:
        # allow grid() with no kwargs
        candidates = plugin.grid()
        candidates = subsample_grid(candidates, max_n=args.max_n, seed=args.seed)
    if len(candidates) > args.max_n:
        candidates = subsample_grid(candidates, max_n=args.max_n, seed=args.seed)

    print(
        f"Grid: {len(candidates)} configs (max_n={args.max_n}, seed={args.seed})",
        flush=True,
    )

    # --- real ---
    print(f"Scoring REAL {plugin.name} grid (no early exit)...", flush=True)
    d_real = plugin.prepare(raw)
    real = score_grid(
        d_real,
        candidates,
        simulate_fn=plugin.simulate,
        classic_pass_fn=plugin.classic_pass,
        soft_pass_fn=plugin.soft_pass,
        costs=COSTS,
        progress_every=args.progress_every,
        label="real",
    )
    primary_key = "n_passers_soft" if plugin.use_soft_primary else "n_passers_classic"
    real["n_passers"] = int(real[primary_key])
    real["primary_n_passers"] = primary_key

    print(
        f"REAL: max_PF(n≥20)={real['max_pf']:.4f} "
        f"primary_passers={real['n_passers']} "
        f"classic={real['n_passers_classic']} soft={real['n_passers_soft']} "
        f"(raw max_PF={real['max_pf_raw']:.1f})",
        flush=True,
    )

    # Frozen slippage sensitivity (report-only; no rescue tuning)
    slip_report: list[dict[str, Any]] = []
    if slip_sensitivity_pts and candidates:
        base_p = dict(candidates[0])
        for sp in slip_sensitivity_pts:
            c2 = dict(COSTS)
            c2["slippage_points"] = float(sp)
            m = plugin.simulate(d_real, **{**c2, **base_p})
            md = metrics_dict(m)
            slip_report.append(
                {
                    "slippage_points": float(sp),
                    "net_profit": md["net_profit"],
                    "profit_factor": md["profit_factor"],
                    "n_trades": md["n_trades"],
                    "max_drawdown_pct": md["max_drawdown_pct"],
                    "soft_pass": bool(plugin.soft_pass(m)) if plugin.soft_pass else None,
                    "classic_pass": bool(plugin.classic_pass(m)),
                }
            )
        print(f"Slippage sensitivity (frozen report-only): {slip_report}", flush=True)

    # Planned vs executed null counts (screen shortcut must not claim 999 ran).
    n_null_planned = int(args.n_null)

    # --- Deterministic SCREEN_FAIL: zero primary passers ---
    # Real passers=0 ⇒ every null trial has n_passers ≥ 0 = real, so hits=n_null
    # and p_n_passers=(n_null+1)/(n_null+1)=1.0 for any finite planned n_null.
    # Skipping trials is arithmetic, not optional early-exit tuning.
    screen_fail_zero_passers = (
        int(real["n_passers"]) == 0
        and not args.quick
        and not non_dispositional
    )
    n_null_executed = n_null_planned
    if screen_fail_zero_passers:
        n_null_executed = 0
        args.n_null = 0
        print(
            "SCREEN_FAIL ZERO_PRIMARY_PASSERS: real primary passers=0 ⇒ "
            "for any planned n_null, every null count ≥ 0 hits the threshold, "
            "so p_n_passers=(n_null+1)/(n_null+1)=1.0. "
            f"Skipping null trials (planned={n_null_planned}, executed=0).",
            flush=True,
        )

    # --- nulls ---
    if int(args.n_null) > 0:
        print(
            f"Running {args.n_null} null trials ({null_method}) with {args.workers} workers...",
            flush=True,
        )
    raw_records = raw.to_dict(orient="records")
    for rec in raw_records:
        t = rec["time"]
        rec["time"] = t.isoformat() if hasattr(t, "isoformat") else str(t)

    # Workers re-load family by the CLI name (builtins + modules).
    family_load_name = args.family
    charter_arg = str(charter_path) if charter_path else None

    null_rows: list[dict] = []
    if args.n_null > 0:
        init_args = (
            raw_records,
            candidates,
            COSTS,
            family_load_name,
            null_method,
            block_days,
            charter_arg,
        )
        if args.workers <= 1:
            _init_worker(*init_args)
            for trial in range(args.n_null):
                row = _null_trial(trial, args.null_seed)
                null_rows.append(row)
                print(
                    f"  null {trial + 1}/{args.n_null}: "
                    f"max_PF={row['max_pf']:.3f} passers={row['n_passers']} "
                    f"classic={row['n_passers_classic']} soft={row['n_passers_soft']} "
                    f"({row['elapsed_s']:.0f}s)",
                    flush=True,
                )
        else:
            with ProcessPoolExecutor(
                max_workers=args.workers,
                initializer=_init_worker,
                initargs=init_args,
            ) as pool:
                futs = {
                    pool.submit(_null_trial, trial, args.null_seed): trial
                    for trial in range(args.n_null)
                }
                done = 0
                for fut in as_completed(futs):
                    row = fut.result()
                    null_rows.append(row)
                    done += 1  # noqa: SIM113
                    print(
                        f"  null done {done}/{args.n_null} (trial {row['trial']}): "
                        f"max_PF={row['max_pf']:.3f} passers={row['n_passers']} "
                        f"({row['elapsed_s']:.0f}s)",
                        flush=True,
                    )
            null_rows.sort(key=lambda r: r["trial"])

    null_max_pf = [r["max_pf"] for r in null_rows]
    null_n_pass = [float(r["n_passers"]) for r in null_rows]
    null_n_classic = [float(r["n_passers_classic"]) for r in null_rows]
    null_n_soft = [float(r["n_passers_soft"]) for r in null_rows]

    p_max_pf = pvalue(null_max_pf, real["max_pf"])
    p_n_passers = pvalue(null_n_pass, float(real["n_passers"]))
    p_n_classic = pvalue(null_n_classic, float(real["n_passers_classic"]))
    p_n_soft = pvalue(null_n_soft, float(real["n_passers_soft"]))

    fail_pf = p_max_pf > 0.05
    fail_pass = p_n_passers > 0.05
    null_pass_dist = dist_summary(null_n_pass)

    if args.quick or non_dispositional:
        disposition = "QUICK_SMOKE_ONLY" if args.quick else "NON_DISPOSITIONAL_OVERRIDE"
        reason = (
            "Quick mode — not a real disposition. Re-run without --quick."
            if args.quick
            else "CLI overrides diverged from frozen charter — not a disposition."
        )
    elif screen_fail_zero_passers:
        disposition = "SCREEN_FAIL"
        reason = (
            "ZERO_PRIMARY_PASSERS: real grid primary passers=0. For any planned "
            "n_null, each null trial has n_passers ≥ 0 = real, so hits=n_null and "
            "p_n_passers=(n_null+1)/(n_null+1)=1.0 under add-one smoothing. "
            f"Null trials not executed (planned={n_null_planned}, executed=0). "
            "p_max_pf not evaluated. Do not retune; freeze a new family_id."
        )
        p_n_passers = 1.0
        p_max_pf = None  # not evaluated — no null PF distribution
        fail_pf = False
        fail_pass = True
    elif fail_pf or fail_pass:
        disposition = plugin.kill_label
        reason = (
            f"Real best-of-{plugin.name}-grid is not distinguishable from "
            f"{null_method} nulls (p_max_pf={p_max_pf:.3f}, "
            f"p_n_passers={p_n_passers:.3f}). The gates measured the search, "
            "not the market. Do not tune further; do not promote."
        )
    elif real["n_passers"] <= null_pass_dist.get("p90", 0):
        disposition = "WEAK_FAIL"
        reason = (
            f"p-values cleared 0.05 but real n_passers={real['n_passers']} is not above "
            f"null p90={null_pass_dist.get('p90', 0):.1f}. Still not evidence of signal; "
            "keep promote=no."
        )
    else:
        disposition = "PASS_KEEP_RESEARCHING"
        reason = (
            f"Real max-stat sits outside the null (p_max_pf={p_max_pf:.3f}, "
            f"p_n_passers={p_n_passers:.3f}). Permission to continue the family "
            "(cut knobs, cross-instrument) — still not live_go / promote."
        )

    attempt_type = (
        "DETERMINISTIC_SCREEN"
        if screen_fail_zero_passers
        else ("QUICK_SMOKE" if args.quick else "SEALED_NULL")
    )
    provenance = build_provenance(
        charter_path=charter_path or Path("none"),
        costs_path=RESEARCH_COSTS_PATH,
        data_path=CSV_PATH,
        null_seed=int(args.null_seed),
        n_null=int(n_null_executed),
        out_dir=out_json.parent,
        require_clean_tree=bool(args.strict_charter and not args.quick),
        extra={
            "null_method": null_method,
            "block_days": block_days,
            "family": plugin.name,
            "disposition": disposition,
            "n_null_planned": int(n_null_planned),
            "n_null_executed": int(n_null_executed),
            "attempt_type": attempt_type,
            "family_screen_attempt": True,  # real develop grid was evaluated
            "sealed_null_attempt": bool(
                n_null_executed > 0 and not args.quick and not non_dispositional
            ),
            "null_trials_executed": int(n_null_executed),
        },
    )

    report = {
        "method": f"{null_method}_maxstat_family",
        "family": plugin.name,
        "family_source": plugin.source,
        "kill_label": plugin.kill_label,
        "charter_path": str(charter_path) if charter_path else None,
        "provenance": provenance,
        "timestamp_utc": pd.Timestamp.now(tz='UTC').isoformat(),
        "window": {
            "holdout_start": str(cutoff),
            "bars": int(len(raw)),
            "start": raw["time"].iloc[0].isoformat(),
            "end": raw["time"].iloc[-1].isoformat(),
        },
        "costs": COSTS,
        "costs_caveat": (
            "commission/spread account-matched for Standard STP; "
            "slippage_points=0 is unmeasured; swap not modeled"
        ),
        "slippage_sensitivity": {
            "role": "report_only_frozen",
            "no_rescue_tuning": True,
            "points": slip_sensitivity_pts,
            "rows": slip_report,
        },
        "grid": {
            "max_n": args.max_n,
            "seed": args.seed,
            "n_configs": len(candidates),
        },
        "gates": {
            "classic": gate_desc_classic,
            "soft": gate_desc_soft if plugin.soft_pass is not None else None,
            "primary_n_passers": primary_key.replace("n_passers_", ""),
            "max_pf_min_trades": MIN_TRADES_MAX_STAT,
            "source": "charter" if charter is not None else "module_or_default",
        },
        "real": real,
        "screen": {
            "zero_primary_passers": bool(screen_fail_zero_passers),
            "rule": (
                "If real primary passers==0, SCREEN_FAIL without null trials. "
                "Reason: every null n_passers ≥ 0 = real, so hits=n_null and "
                "p_n_passers=(n_null+1)/(n_null+1)=1.0 for any planned n_null."
            ),
        },
        "attempt_accounting": {
            "attempt_type": attempt_type,
            "family_screen_attempt": True,
            "sealed_null_attempt": bool(
                n_null_executed > 0 and not args.quick and not non_dispositional
            ),
            "n_null_planned": int(n_null_planned),
            "n_null_executed": int(n_null_executed),
            "null_trials_executed": int(n_null_executed),
            "r1_style_null_burned": bool(n_null_executed > 0 and not args.quick),
        },
        "null": {
            "method": null_method,
            "block_days": block_days,
            "n_trials": int(n_null_executed),
            "n_null_planned": int(n_null_planned),
            "n_null_executed": int(n_null_executed),
            "skipped_reason": (
                "ZERO_PRIMARY_PASSERS" if screen_fail_zero_passers else None
            ),
            "base_seed": args.null_seed,
            "workers": args.workers,
            "max_pf": dist_summary(null_max_pf) if null_rows else None,
            "n_passers": null_pass_dist if null_rows else None,
            "n_passers_classic": dist_summary(null_n_classic) if null_rows else None,
            "n_passers_soft": dist_summary(null_n_soft) if null_rows else None,
            "p_max_pf": p_max_pf,  # None when screen-fail (not evaluated)
            "p_n_passers": p_n_passers,
            "p_n_passers_classic": p_n_classic if null_rows else None,
            "p_n_passers_soft": p_n_soft if null_rows else None,
            "p_max_pf_status": (
                "not_evaluated" if screen_fail_zero_passers else "evaluated"
            ),
            "p_n_passers_status": (
                "implied_1.0_zero_real_passers"
                if screen_fail_zero_passers
                else "evaluated"
            ),
            "trials": null_rows,
        },
        "verdict": {
            "disposition": disposition,
            "reason": reason,
            "fail_max_pf": fail_pf,
            "fail_n_passers": fail_pass,
            "promote": False,
            "live_go": False,
            "screen_status": (
                "ZERO_PRIMARY_PASSERS" if screen_fail_zero_passers else None
            ),
        },
        "elapsed_s": float(time.time() - t_all),
        "quick": bool(args.quick),
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, default=str) + "\n")
    write_markdown(report, out_md)

    print(flush=True)
    print(f"Disposition: {disposition}", flush=True)
    print(reason, flush=True)
    try:
        jrel, mrel = out_json.relative_to(ROOT), out_md.relative_to(ROOT)
    except ValueError:
        jrel, mrel = out_json, out_md
    print(f"Wrote {jrel} and {mrel}", flush=True)
    print(f"Total elapsed: {report['elapsed_s']:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
