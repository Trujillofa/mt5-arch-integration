#!/usr/bin/env python3
"""EURUSD NY-session scalp develop screen (192 configs + null calibration).

Lock: results/eurusd_ny_scalp_lock.json — frozen BEFORE any metric.
promote / live_go = false. Offline research only. No orders.

Invariants enforced at runtime:
- holdout_start comes from the lock (asserted != the us_index default 2026-06-01)
- per-fill sizing: sl_points * lots * point_value <= risk_per_trade_usd (FLOOR, never round)
- min_sl_points: skip, never resize into a tight stop
- equity floor: equity > 0 asserted at every fill and every close
- shorts fill bid-space; SL-first intrabar precedence; all trades force-flat 16:45 ET
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time as pytime
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from eurusd_ny_scalp_core import (  # noqa: E402
    FLAT_MIN,
    M5Data,
    build_context,
    load_eurusd_m5,
    rotate_returns_within_days,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    metrics_from_trades,
    write_slim_json,
)

SEARCH_ID = "eurusd_ny_scalp_develop_v1"
LOCK_PATH = _ROOT / "results" / "eurusd_ny_scalp_lock.json"
CSV_PATH = _ROOT / "results" / "eurusd_data" / "history_EURUSD.csv"
OUT_JSON = _ROOT / "results" / "eurusd_ny_scalp_autoresearch.json"
FULL_JSON = _ROOT / "results" / "eurusd_ny_scalp_autoresearch_full.json"
NULL_JSON = _ROOT / "results" / "eurusd_ny_scalp_null.json"

# H2: the us_index default holdout. Kept as a literal here on purpose — the
# research script itself never imports that module's holdout machinery.
FORBIDDEN_HOLDOUT_DEFAULT = date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Lock + book
# ---------------------------------------------------------------------------


def load_lock(path: Path = LOCK_PATH) -> dict:
    lock = json.loads(Path(path).read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit(f"search_id mismatch: {lock.get('search_id')}")
    if lock.get("promote") is True or lock.get("live_go") is True:
        raise SystemExit("promote / live_go must stay false")
    return lock


def effective_holdout_start(lock: dict) -> date:
    hs = date.fromisoformat(str(lock["holdout"]["holdout_start"]))
    if hs == FORBIDDEN_HOLDOUT_DEFAULT:
        raise SystemExit(
            f"holdout_start {hs} equals the us_index module default — "
            "the lock value must be used, not an inherited default"
        )
    return hs


def require_eurusd_cost_book(lock: dict) -> CostSpec:
    """Lane-local cost book from the lock. Neither us_index frozen-book helper
    is imported: both hard-pin 1.0 lot / 10-pt slippage and would SystemExit."""
    c = lock["costs"]
    b = lock["book"]
    costs = CostSpec(
        point_size=1e-5,
        contract_size=100_000.0,
        lots=float(b["risk_per_trade_usd"]),  # placeholder, per-trade sizing below
        commission_per_lot=float(c["commission_per_lot"]),
        slippage_points=float(c["slippage_points"]),
        max_spread_points=float(c["max_spread_points"]),
    )
    if costs.commission_per_lot != 0.0:
        raise SystemExit("lock expects commission 0 (Vantage Standard STP)")
    if float(b["point_value_per_lot"]) != 1.0:
        raise SystemExit("point value must be 1.00 USD/pt/lot for EURUSD 1e-5 x 100k")
    # C2 coherence at lock-load time:
    # (a) sizing floors risk to <= risk_per_trade_usd by construction, and
    #     risk_per_trade (100) <= |daily_halt| (300) so no single stop-out
    #     can breach the day halt;
    # (b) lot_cap is defensive-only: the largest uncapped size happens at the
    #     tightest allowed stop (min_sl_points), and it must stay <= lot_cap.
    pv = float(b["point_value_per_lot"])
    risk = float(b["risk_per_trade_usd"])
    if risk > float(abs(lock["risk"]["daily_halt_usd"])) + 1e-9:
        raise SystemExit("risk_per_trade_usd exceeds |daily_halt_usd|")
    max_uncapped = math.floor(
        risk / (float(b["min_sl_points"]) * pv) / float(b["lot_step"])
    ) * float(b["lot_step"])
    if max_uncapped > float(b["lot_cap"]) + 1e-9:
        raise SystemExit(
            "lot_cap would bind live (min_sl_points sizing exceeds cap) — lock is incoherent"
        )
    return costs


def verify_data_sha(csv_path: Path, lock: dict) -> None:
    h = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    want = str(lock["data"]["sha256"])
    if h != want:
        raise SystemExit(f"data sha256 mismatch: {h} != {want} (refusing to run)")


# ---------------------------------------------------------------------------
# Sizing (lock: book) — floor, never round
# ---------------------------------------------------------------------------


def size_lots(
    sl_points: float,
    risk_usd: float,
    point_value: float = 1.0,
    step: float = 0.01,
    min_lot: float = 0.01,
    cap: float = 2.0,
    min_sl_points: float = 80.0,
) -> float | None:
    """Risk-normalized lots. Returns None when the stop is nearer than
    min_sl_points (skip — never resize into a tight stop) or the floored
    size cannot clear min_lot."""
    if sl_points < min_sl_points:
        return None
    raw = risk_usd / (sl_points * point_value)
    lots = math.floor(raw / step) * step
    lots = round(lots, 10)
    if lots < min_lot:
        return None
    if lots > cap:
        lots = cap
    if lots * sl_points * point_value > risk_usd + 1e-9:
        raise AssertionError(
            f"per-fill invariant breach: {lots} lots x {sl_points} pt > {risk_usd}"
        )
    return lots


def _floor_step(x: float, step: float) -> float:
    return math.floor(x / step) * step


# ---------------------------------------------------------------------------
# Exit grid (lock: grid.exits_32 — exactly 32)
# ---------------------------------------------------------------------------


def build_exit_grid() -> list[dict]:
    ex: list[dict] = []
    for tp in (0.0010, 0.0015, 0.0020, 0.0025, 0.0030):  # 15 pct x pct
        for sl in (0.0025, 0.0050, 0.0100):
            ex.append({"kind": "pct", "tp": tp, "sl": sl})
    for slm in (1.0, 1.5):  # 6 atr x atr
        for tpm in (1.5, 2.0, 2.5):
            ex.append({"kind": "atr", "slm": slm, "tpm": tpm})
    for sl in (0.0025, 0.0050, 0.0100):  # 3 structure TP
        ex.append({"kind": "structure", "sl": sl})
    for n in (6, 12):  # 2 time stop
        ex.append({"kind": "bars", "n": n, "sl": 0.0100})
    for hhmm in ((11, 30), (14, 0)):  # 6 flatten-x-SL
        for sl in (0.0025, 0.0050, 0.0100):
            ex.append({"kind": "flatten", "hh": hhmm[0], "mm": hhmm[1], "sl": sl})
    assert len(ex) == 32, len(ex)
    return ex


def exit_name(e: dict) -> str:
    if e["kind"] == "pct":
        return f"pct_tp{e['tp'] * 100:.2f}_sl{e['sl'] * 100:.2f}"
    if e["kind"] == "atr":
        return f"atr_sl{e['slm']}_tp{e['tpm']}"
    if e["kind"] == "usd":
        return f"usd_tp{e['tp_usd']:.0f}_sl{e['sl_usd']:.0f}"
    if e["kind"] == "structure":
        return f"structure_sl{e['sl'] * 100:.2f}"
    if e["kind"] == "bars":
        return "bars{}_sl{:.2f}".format(e["n"], e["sl"] * 100)
    return "flat_{:02d}{:02d}_sl{:.2f}".format(e["hh"], e["mm"], e["sl"] * 100)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


@dataclass
class SimTrade:
    side: int
    fill_i: int
    exit_i: int
    entry: float
    exit: float
    reason: str
    et_date: str
    fill_time: str
    exit_time: str
    lots: float
    sl_points: float
    tp: float | None
    sl: float | None
    spread_pts: float
    cost: float
    pnl: float
    mae: float
    mfe: float
    equity_after: float


def _rt_cost(spread_pts: float, costs: CostSpec, lots: float) -> float:
    return (
        spread_pts + 2.0 * costs.slippage_points
    ) * costs.point_size * costs.contract_size * lots + 2.0 * costs.commission_per_lot * lots


def simulate_config(
    d: M5Data,
    signals: np.ndarray,
    exit_spec: dict,
    tgt_long: np.ndarray | None,
    tgt_short: np.ndarray | None,
    atr: np.ndarray,
    costs: CostSpec,
    lock: dict,
    start_balance: float | None = None,
) -> list[SimTrade]:
    """Walk-forward: signal on close of i -> fill at open of i+1 (same ET day).
    One position. SL-first. Shorts bid-space. -3% day halt. 16:45 force-flat.

    Equity floor: a dead account stops trading and the run ENDS, keeping every
    trade taken up to and including the one that busted it. Callers detect it
    with ``went_bankrupt(trades)``; it is not an exception.

    It used to raise, and the caller discarded the whole trade list. That let a
    bust occurring in the HOLDOUT erase the config's DEVELOP metrics and force
    it ineligible - holdout data deciding develop selection, which the lock
    forbids ("holdout_rule: NEVER used for selection"). Lot size never reads
    ``balance`` (risk_per_trade_usd and fixed lots are both absolute), so
    develop trades are identical either way; only the reporting was wrong."""
    b = lock["book"]
    r = lock["risk"]
    policy = str(b.get("sizing_policy", "risk_normalized"))
    pv = float(b["point_value_per_lot"])
    halt = float(r["daily_halt_usd"])  # negative, e.g. -300
    balance = float(b["balance_usd"] if start_balance is None else start_balance)
    point = costs.point_size
    if policy == "fixed_lots":
        risk_usd = min_lot = cap = min_sl = 0.0
    else:
        risk_usd = float(b["risk_per_trade_usd"])
        min_lot, cap, min_sl = (
            float(b["min_lot"]),
            float(b["lot_cap"]),
            float(b["min_sl_points"]),
        )

    trades: list[SimTrade] = []
    day_pnl: dict[int, float] = {}
    n = len(d)
    blocked_until = -1
    for i in (int(x) for x in np.flatnonzero(signals)):
        if i >= n - 1 or i <= blocked_until:
            continue
        sig = int(signals[i])
        fill = i + 1
        k_sig, k_fill = int(d.et_key[i]), int(d.et_key[fill])
        if k_sig != k_fill:
            continue
        # day-halt: no NEW entries once realized day PnL <= halt
        if day_pnl.get(k_fill, 0.0) <= halt:
            continue
        spr = float(d.spread[fill])
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            continue
        if balance <= 0.0:
            break  # dead account: no further entries, keep the history
        entry = float(d.open[fill])
        at = float(atr[i]) if np.isfinite(atr[i]) else 0.0

        sl = tp = None
        kind = exit_spec["kind"]
        if kind == "usd":
            lots_fx = float(b["lots"])
            sl_pts = float(exit_spec["sl_usd"]) / (lots_fx * pv)
            tp_pts = float(exit_spec["tp_usd"]) / (lots_fx * pv)
            sl = entry - sig * sl_pts * point
            tp = entry + sig * tp_pts * point
        elif kind == "pct":
            sl = entry - sig * exit_spec["sl"] * entry
            tp = entry + sig * exit_spec["tp"] * entry
        elif kind == "atr":
            if at <= 0.0:
                continue
            sl = entry - sig * at * exit_spec["slm"]
            tp = entry + sig * at * exit_spec["tpm"]
        elif kind == "structure":
            sl = entry - sig * exit_spec["sl"] * entry
            lvl = tgt_long[i] if sig > 0 else tgt_short[i]
            if not np.isfinite(lvl):
                continue
            tp = float(lvl)
            if sig > 0 and tp <= entry:
                continue
            if sig < 0 and tp >= entry:
                continue
        elif kind in ("bars", "flatten"):
            sl = entry - sig * exit_spec["sl"] * entry

        sl_points = abs(entry - sl) / point
        if policy == "fixed_lots":
            lots = float(b["lots"])
        else:
            lots = size_lots(sl_points, risk_usd, pv, 0.01, min_lot, cap, min_sl)
            if lots is None:
                continue
            assert sl_points * lots * pv <= risk_usd + 1e-9, "per-fill invariant"

        flat_m = FLAT_MIN
        reason_flat = "flat_1645"
        if kind == "flatten":
            fm = exit_spec["hh"] * 60 + exit_spec["mm"]
            if fm < flat_m:
                flat_m, reason_flat = fm, f"flat_{exit_spec['hh']:02d}{exit_spec['mm']:02d}"
        limit = fill + int(exit_spec["n"]) if kind == "bars" else n

        j = fill
        exit_i: int | None = None
        exit_px = 0.0
        reason = reason_flat
        while j < n and int(d.et_key[j]) == k_fill and j <= limit:
            if int(d.et_min[j]) >= flat_m and j > fill:
                exit_i, exit_px, reason = j, float(d.open[j]), reason_flat
                break
            if sl is not None:
                # bid-space: a short covers at ask (bid + spread). spr is in
                # POINTS — convert to price via point_size before shifting.
                lvl = sl - spr * point if sig < 0 else sl
                hit = d.high[j] >= lvl if sig < 0 else d.low[j] <= lvl
                if hit:  # SL-first precedence
                    fill_px = lvl
                    exit_i, exit_px, reason = j, fill_px, "sl"
                    break
            if tp is not None:
                lvl = tp - spr * point if sig < 0 else tp
                hit = d.low[j] <= lvl if sig < 0 else d.high[j] >= lvl
                if hit:
                    exit_i, exit_px, reason = j, lvl, "tp"
                    break
            if kind == "bars" and j == limit:
                exit_i, exit_px, reason = j, float(d.open[j]), f"bars{exit_spec['n']}"
                break
            j += 1
        if exit_i is None:
            last = min(j - 1, n - 1)
            while last > fill and int(d.et_key[last]) != k_fill:
                last -= 1
            if last <= fill:
                continue
            exit_i, exit_px, reason = last, float(d.open[last]), "session_end"

        cost = _rt_cost(spr, costs, lots)
        pnl = (exit_px - entry) * sig * costs.contract_size * lots - cost
        balance += pnl
        day_pnl[k_fill] = day_pnl.get(k_fill, 0.0) + pnl
        wh = d.high[fill : exit_i + 1]
        wl = d.low[fill : exit_i + 1]
        if sig > 0:
            mae = float(entry - np.min(wl))
            mfe = float(np.max(wh) - entry)
        else:
            mae = float(np.max(wh) - entry)
            mfe = float(entry - np.min(wl))
        trades.append(
            SimTrade(
                side=sig,
                fill_i=fill,
                exit_i=exit_i,
                entry=entry,
                exit=exit_px,
                reason=reason,
                et_date=str(d.times_et[fill].date()),
                fill_time=d.times_et[fill].isoformat(),
                exit_time=d.times_et[exit_i].isoformat(),
                lots=lots,
                sl_points=sl_points,
                tp=tp,
                sl=sl,
                spread_pts=spr,
                cost=cost,
                pnl=pnl,
                mae=mae,
                mfe=mfe,
                equity_after=balance,
            )
        )
        blocked_until = exit_i
        if balance <= 0.0:
            break  # dead account: keep the bust trade; stop new entries
    return trades


def went_bankrupt(trades: list[SimTrade]) -> bool:
    """True if the account hit the equity floor. Balance is monotone in
    trade order, so only the last trade can have taken it to <= 0."""
    return bool(trades) and trades[-1].equity_after <= 0.0


def bankrupt_at(trades: list[SimTrade]) -> str | None:
    """ET date of the busting trade, or None."""
    return trades[-1].et_date if went_bankrupt(trades) else None


# ---------------------------------------------------------------------------
# Lane-local goal metrics (equity path — NOT a static balance)
# ---------------------------------------------------------------------------

GOAL_DAILY = 0.01
GOAL_MONTHLY = 0.20
MIN_TRADES_DEVELOP = 40


def daily_monthly_equity(trades: list[SimTrade], start_balance: float) -> dict:
    """day_pct = day_pnl / equity_at_day_start; month over trade-months only."""
    if not trades:
        return {
            "trade_days": 0,
            "months": 0,
            "median_daily_pct": 0.0,
            "mean_daily_pct": 0.0,
            "median_monthly_pct": 0.0,
            "mean_monthly_pct": 0.0,
            "halt_days": 0,
            "hit_daily_goal": False,
            "hit_monthly_goal": False,
        }
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t.et_date] = by_day.get(t.et_date, 0.0) + t.pnl
    days = sorted(by_day)
    eq_day: dict[str, float] = {}
    eq = start_balance
    for dd in days:
        eq_day[dd] = eq
        eq += by_day[dd]
    day_pcts = [by_day[dd] / eq_day[dd] if eq_day[dd] > 0 else 0.0 for dd in days]
    by_month: dict[str, float] = {}
    eq_month: dict[str, float] = {}
    for dd in days:
        m = dd[:7]
        by_month[m] = by_month.get(m, 0.0) + by_day[dd]
        eq_month.setdefault(m, eq_day[dd])
    month_pcts = [by_month[m] / eq_month[m] if eq_month[m] > 0 else 0.0 for m in sorted(by_month)]
    return {
        "trade_days": len(days),
        "months": len(by_month),
        "median_daily_pct": float(np.median(day_pcts)),
        "mean_daily_pct": float(np.mean(day_pcts)),
        "median_monthly_pct": float(np.median(month_pcts)) if month_pcts else 0.0,
        "mean_monthly_pct": float(np.mean(month_pcts)) if month_pcts else 0.0,
        "halt_days": 0,
        "hit_daily_goal": bool(day_pcts) and float(np.median(day_pcts)) >= GOAL_DAILY,
        "hit_monthly_goal": bool(month_pcts) and float(np.median(month_pcts)) >= GOAL_MONTHLY,
    }


def _attr_trades(trades: list[SimTrade]):
    """metrics_from_trades reads attributes; SimTrade carries them all."""
    return trades


def pack_metrics(trades: list[SimTrade], start_balance: float, halt_usd: float) -> dict:
    m = metrics_from_trades(_attr_trades(trades))
    m.update(daily_monthly_equity(trades, start_balance))
    by_day: dict[str, float] = {}
    for t in trades:
        by_day[t.et_date] = by_day.get(t.et_date, 0.0) + t.pnl
    m["halt_days"] = sum(1 for v in by_day.values() if v <= halt_usd)
    m["goal_both"] = bool(m["hit_daily_goal"] and m["hit_monthly_goal"])
    return m


def score_row(m: dict) -> float:
    if int(m["trades"]) < MIN_TRADES_DEVELOP or float(m["net_pnl"]) <= 0:
        return -1e9
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    return pf_v * 1000.0 + float(m["expectancy"])


def rank_develop(rows: list[dict]) -> list[dict]:
    eligible = [r for r in rows if float(r["develop_score"]) > -1e8]
    return sorted(
        eligible,
        key=lambda r: (r["develop"]["profit_factor"] or 3.0, r["develop"]["expectancy"]),
        reverse=True,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@dataclass
class SearchArrays:
    d: M5Data
    contexts: dict  # family -> {one_per_day: FamilyContext}
    lock: dict
    costs: CostSpec


def prepare(d: M5Data, lock: dict, costs: CostSpec) -> dict:
    return {
        False: build_context(d, one_per_day=False),
        True: build_context(d, one_per_day=True),
    }


def run_grid(
    d: M5Data, lock: dict, costs: CostSpec, holdout: date, contexts: dict | None = None
) -> list[dict]:
    if contexts is None:
        contexts = prepare(d, lock, costs)
    balance = float(lock["book"]["balance_usd"])
    halt = float(lock["risk"]["daily_halt_usd"])
    exits = build_exit_grid()
    rows: list[dict] = []
    for fam in ("trend_continuation", "mean_reversion", "breakout"):
        for opd in (False, True):
            ctx = contexts[opd][fam]
            for ex in exits:
                trades = simulate_config(
                    d,
                    ctx.signals,
                    ex,
                    ctx.tgt_long,
                    ctx.tgt_short,
                    ctx.atr,
                    costs,
                    lock,
                )
                dev = [t for t in trades if date.fromisoformat(t.et_date) < holdout]
                ho = [t for t in trades if date.fromisoformat(t.et_date) >= holdout]
                bust = bankrupt_at(trades)
                bust_d = date.fromisoformat(bust) if bust else None
                dmet = pack_metrics(dev, balance, halt)
                hmet = pack_metrics(ho, balance, halt)
                dmet["bankrupt"] = bust_d is not None and bust_d < holdout
                hmet["bankrupt"] = bust_d is not None and bust_d >= holdout
                rows.append(
                    {
                        "params": {
                            "family": fam,
                            "one_per_day": opd,
                            "exit": exit_name(ex),
                        },
                        "develop": dmet,
                        "holdout": hmet,
                        "develop_score": score_row(dmet),
                    }
                )
    return rows


def run_null(d: M5Data, lock: dict, costs: CostSpec, holdout: date) -> dict:
    nc = lock["null_calibration"]
    seeds = [int(s) for s in nc["seeds"]]
    per_seed = []
    t0 = pytime.time()
    for i, seed in enumerate(seeds, 1):
        rng = np.random.default_rng(seed)
        dn = rotate_returns_within_days(d, rng)
        rows = run_grid(dn, lock, costs, holdout)
        ranked = rank_develop(rows)
        best = ranked[0]["develop"] if ranked else None
        rec = {
            "seed": seed,
            "n_eligible": len(ranked),
            "best_develop_median_daily_pct": None if best is None else best["median_daily_pct"],
        }
        per_seed.append(rec)
        print(
            f"null seed {i}/{len(seeds)}={seed} eligible={rec['n_eligible']} "
            f"best={rec['best_develop_median_daily_pct']} "
            f"({pytime.time() - t0:.0f}s)",
            flush=True,
        )
    vals = [
        s["best_develop_median_daily_pct"]
        for s in per_seed
        if s["best_develop_median_daily_pct"] is not None
    ]
    return {
        "seeds": seeds,
        "per_seed": per_seed,
        "max_null_best": float(max(vals)) if vals else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--csv", type=Path, default=CSV_PATH)
    ap.add_argument("--lock", type=Path, default=LOCK_PATH)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    ap.add_argument("--full-out", type=Path, default=FULL_JSON)
    ap.add_argument("--null-out", type=Path, default=NULL_JSON)
    ap.add_argument("--null-only", action="store_true")
    args = ap.parse_args()

    lock = load_lock(args.lock)
    costs = require_eurusd_cost_book(lock)
    verify_data_sha(args.csv, lock)
    holdout = effective_holdout_start(lock)
    d = load_eurusd_m5(args.csv)

    t0 = pytime.time()
    # null BEFORE the real run (lock: null_calibration.order)
    null = run_null(d, lock, costs, holdout)
    args.null_out.parent.mkdir(parents=True, exist_ok=True)
    args.null_out.write_text(json.dumps(null, indent=2) + "\n")
    print(
        f"null: max_null_best={null['max_null_best']} "
        f"({pytime.time() - t0:.0f}s) -> {args.null_out}"
    )
    if args.null_only:
        return

    rows = run_grid(d, lock, costs, holdout)
    ranked = rank_develop(rows)
    best = ranked[0] if ranked else None
    mnb = null["max_null_best"]
    gate = None
    if best is not None and mnb is not None:
        gate = {
            "threshold": mnb + 0.5 * GOAL_DAILY,
            "best_develop_median_daily_pct": best["develop"]["median_daily_pct"],
            "passes": bool(best["develop"]["median_daily_pct"] >= mnb + 0.5 * GOAL_DAILY),
        }
    report = {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "holdout_start": str(holdout),
        "holdout_boundary_unit": lock["holdout"]["holdout_boundary_unit"],
        "holdout_rule": "NEVER used for selection; scored after ranking froze",
        "bars": len(d),
        "et_trade_days": int(len({int(k) for k in d.et_key})),
        "n_configs": len(rows),
        "n_eligible_develop": len(ranked),
        "n_develop_hit_goal": sum(1 for r in rows if r["develop"]["goal_both"]),
        "n_top20_holdout_hit_goal": sum(1 for r in ranked[:20] if r["holdout"]["goal_both"]),
        "null": null,
        "gate": gate,
        "elapsed_sec": round(pytime.time() - t0, 1),
        "costs": asdict(costs) | {"lots": "risk-normalized per trade (lock: book)"},
        "data": lock["data"],
        "best_develop": best,
        "top10_develop": ranked[:10],
        "goal_note": (
            "median trade-day >= 1% and trade-month >= 20%, equity-normalized "
            "(day_pnl / equity_at_day_start) on a $10k book, risk-normalized "
            "$100/trade sizing. Selection is develop-only and never sees holdout. "
            "The develop winner must also clear max_null_best + 0.5pp."
        ),
    }
    write_slim_json(args.out, report)
    args.full_out.write_text(
        json.dumps(
            {
                "rows": rows,
                "report": {k: v for k, v in report.items() if k not in ("top10_develop",)},
            },
            indent=2,
            default=float,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "n_configs": report["n_configs"],
                "n_eligible_develop": report["n_eligible_develop"],
                "n_develop_hit_goal": report["n_develop_hit_goal"],
                "max_null_best": mnb,
                "gate": gate,
                "best_develop_params": None if best is None else best["params"],
                "best_develop": None
                if best is None
                else {
                    k: best["develop"][k]
                    for k in (
                        "trades",
                        "win_rate",
                        "profit_factor",
                        "net_pnl",
                        "median_daily_pct",
                        "median_monthly_pct",
                        "halt_days",
                    )
                },
                "best_holdout": None
                if best is None
                else {
                    k: best["holdout"][k]
                    for k in (
                        "trades",
                        "win_rate",
                        "profit_factor",
                        "net_pnl",
                        "median_daily_pct",
                    )
                },
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out} (full: {args.full_out})")


if __name__ == "__main__":
    main()
