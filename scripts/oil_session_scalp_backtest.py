#!/usr/bin/env python3
"""Replay / transfer controls for the oil session scalp lane.

Search families use ATR SL + R-multiple TP + time-stop + box flatten.
Transfer controls (never ranked):
  index_transfer     — frozen ny_cash_orb_vwap_ema_flat, flatten 15:45 ET
  gold_transfer      — London 30m OR + NY metals, flatten 11:00 local box
  btc_transfer       — BTC NY VWAP+EMA on the oil NY box, flatten 11:30 ET
  eurusd_mr_transfer — EURUSD BB+RSI mean_reversion, flatten 16:45 ET

SAFETY: offline only. promote / live_go = no.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from oil_session_scalp_core import (  # noqa: E402
    FAM_LONDON,
    LONDON_END_MIN,
    M5Data,
    NY_FLAT_MIN,
    assert_lane_holdout,
    btc_transfer_signals,
    eurusd_mr_transfer_signals,
    family_signals,
    flatten_spec_for_family,
    gold_transfer_signals,
    index_transfer_signals,
    in_london_entry,
    load_oil_m5,
    wilder_atr,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    _round_trip_cost,
    metrics_from_trades,
    write_slim_json,
)

LOCK_PATH = _ROOT / "results" / "oil_session_scalp_lock.json"
INDEX_FLAT_MIN = 15 * 60 + 45
GOLD_FLAT_MIN_ET = 11 * 60
EURUSD_FLAT_MIN = 16 * 60 + 45


def load_lock(path: Path = LOCK_PATH) -> dict:
    return json.loads(path.read_text())


def require_oil_cost_book(lock: dict, costs: CostSpec, *, allow_pending: bool = False) -> None:
    if lock.get("promote") is True:
        raise SystemExit("promote must stay false")
    if lock.get("live_go") is True:
        raise SystemExit("live_go must stay false")
    book = lock.get("book") or {}
    lc = lock.get("costs") or {}
    if not allow_pending:
        if lc.get("status") == "pending_m5_measure":
            raise SystemExit("costs still pending_m5_measure — stamp the lock before replay")
        if float(book.get("contract_size") or 0) <= 0:
            raise SystemExit("book.contract_size not stamped from SymbolInfo")
        if not (lock.get("data") or {}).get("sha256"):
            raise SystemExit("data.sha256 empty — export M5 and stamp the lock first")
    if float(book.get("lots", costs.lots)) != float(costs.lots):
        raise SystemExit("lots mutated vs lock")
    if abs(float(lc["slippage_points"]) - float(costs.slippage_points)) > 1e-9:
        raise SystemExit("slippage_points mutated vs lock")
    if abs(float(lc["max_spread_points"]) - float(costs.max_spread_points)) > 1e-9:
        raise SystemExit("max_spread_points mutated vs lock")
    if abs(float(book["point_size"]) - float(costs.point_size)) > 1e-12:
        raise SystemExit("point_size mutated vs lock")
    if abs(float(book["contract_size"]) - float(costs.contract_size)) > 1e-12:
        raise SystemExit("contract_size mutated vs lock")


def costs_from_lock(lock: dict) -> CostSpec:
    book = lock["book"]
    c = lock["costs"]
    return CostSpec(
        point_size=float(book["point_size"]),
        contract_size=float(book["contract_size"]),
        lots=float(book["lots"]),
        commission_per_lot=float(c["commission_per_lot"]),
        slippage_points=float(c["slippage_points"]),
        max_spread_points=float(c["max_spread_points"]),
    )


def holdout_start_from_lock(lock: dict) -> date:
    hs = date.fromisoformat(lock["holdout"]["start"])
    assert_lane_holdout(hs)
    return hs


def split_by_holdout(trades: list[Trade], holdout_start: date) -> tuple[list[Trade], list[Trade]]:
    pre = [t for t in trades if date.fromisoformat(t.et_date) < holdout_start]
    post = [t for t in trades if date.fromisoformat(t.et_date) >= holdout_start]
    return pre, post


def _flatten_hit(d: M5Data, j: int, clock: str, flatten_min: int, fill: int) -> bool:
    if clock == "london":
        return int(d.lon_min[j]) >= flatten_min
    if clock == "et":
        return int(d.et_min[j]) >= flatten_min
    if clock == "box":
        if in_london_entry(d)[fill] if fill < len(d) else False:
            return int(d.lon_min[j]) >= LONDON_END_MIN
        return int(d.et_min[j]) >= NY_FLAT_MIN
    raise ValueError(f"unknown flatten clock {clock}")


def simulate_exits(
    d: M5Data,
    signals: np.ndarray,
    costs: CostSpec,
    *,
    sl_atr: float | None,
    tp_r: float | None,
    time_stop_bars: int | None,
    flatten_min: int = NY_FLAT_MIN,
    flatten_clock: str = "et",
    flatten_reason: str = "flat_box",
) -> list[Trade]:
    """Signal on close of i, fill open of i+1, SL-first, same ET day, one position."""
    atr = wilder_atr(d.high, d.low, d.close, 14)
    trades: list[Trade] = []
    n = len(d)
    blocked = -1
    point = costs.point_size
    for i in (int(x) for x in np.flatnonzero(signals)):
        if i >= n - 1 or i <= blocked:
            continue
        sig = int(signals[i])
        fill = i + 1
        if int(d.et_key[i]) != int(d.et_key[fill]):
            continue
        spr = float(d.spread[fill])
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            continue
        entry = float(d.open[fill])
        at = float(atr[i]) if np.isfinite(atr[i]) else 0.0
        sl = tp = None
        if sl_atr is not None:
            if at <= 0.0:
                continue
            sl = entry - sig * at * float(sl_atr)
            if tp_r is not None:
                r = abs(entry - sl)
                tp = entry + sig * r * float(tp_r)
        limit = fill + int(time_stop_bars) if time_stop_bars else n
        j = fill
        exit_i: int | None = None
        exit_px = 0.0
        reason = flatten_reason
        k_fill = int(d.et_key[fill])
        while j < n and int(d.et_key[j]) == k_fill and j <= limit:
            if j > fill and _flatten_hit(d, j, flatten_clock, flatten_min, fill):
                exit_i, exit_px, reason = j, float(d.open[j]), flatten_reason
                break
            if sl is not None:
                lvl = sl - spr * point if sig < 0 else sl
                hit = d.high[j] >= lvl if sig < 0 else d.low[j] <= lvl
                if hit:
                    op_j = float(d.open[j])
                    fill_px = min(lvl, op_j) if sig > 0 else max(lvl, op_j)
                    exit_i, exit_px, reason = j, fill_px, "sl"
                    break
            if tp is not None:
                lvl = tp - spr * point if sig < 0 else tp
                hit = d.low[j] <= lvl if sig < 0 else d.high[j] >= lvl
                if hit:
                    exit_i, exit_px, reason = j, lvl, "tp"
                    break
            if time_stop_bars is not None and j == limit:
                exit_i, exit_px, reason = j, float(d.open[j]), f"bars{time_stop_bars}"
                break
            j += 1
        if exit_i is None:
            last = min(j - 1, n - 1)
            while last > fill and int(d.et_key[last]) != k_fill:
                last -= 1
            if last <= fill:
                continue
            exit_i, exit_px, reason = last, float(d.open[last]), "session_end"
        cost = _round_trip_cost(spr, costs)
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        wh = d.high[fill : exit_i + 1]
        wl = d.low[fill : exit_i + 1]
        if sig > 0:
            mae = float(entry - np.min(wl))
            mfe = float(np.max(wh) - entry)
        else:
            mae = float(np.max(wh) - entry)
            mfe = float(entry - np.min(wl))
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill,
                exit_i=int(exit_i),
                entry=entry,
                exit=float(exit_px),
                reason=reason,
                et_date=str(d.times_et[fill].date()),
                signal_time=d.times_et[i].isoformat(),
                fill_time=d.times_et[fill].isoformat(),
                exit_time=d.times_et[exit_i].isoformat(),
                spread_pts=spr,
                cost=cost,
                pnl=float(pnl),
                mae=mae,
                mfe=mfe,
            )
        )
        blocked = int(exit_i)
    return trades


def pack_slices(trades: list[Trade], holdout_start: date) -> dict:
    pre, post = split_by_holdout(trades, holdout_start)
    return {
        "all": metrics_from_trades(trades),
        "develop": metrics_from_trades(pre),
        "holdout": metrics_from_trades(post),
        "signals": len(trades),
    }


def run_family(
    d: M5Data,
    lock: dict,
    costs: CostSpec,
    family: str,
    *,
    sl_atr: float,
    tp_r: float,
    time_stop_bars: int,
    min_atr_pct: float,
    eia_blackout: bool,
) -> tuple[dict, list[Trade]]:
    sigs = family_signals(
        d, family, min_atr_pct=min_atr_pct, eia_blackout=eia_blackout
    )
    clock, fmin = flatten_spec_for_family(family)
    trades = simulate_exits(
        d,
        sigs,
        costs,
        sl_atr=sl_atr,
        tp_r=tp_r,
        time_stop_bars=time_stop_bars,
        flatten_min=fmin,
        flatten_clock=clock,
        flatten_reason=f"flat_{clock}",
    )
    hs = holdout_start_from_lock(lock)
    out = pack_slices(trades, hs)
    out.update(
        {
            "family_id": family,
            "params": {
                "sl_atr": sl_atr,
                "tp_r": tp_r,
                "time_stop_bars": time_stop_bars,
                "min_atr_pct": min_atr_pct,
                "eia_blackout": eia_blackout,
            },
            "promote": False,
            "live_go": False,
        }
    )
    return out, trades


def run_transfers(d: M5Data, lock: dict, costs: CostSpec) -> dict:
    hs = holdout_start_from_lock(lock)
    idx = simulate_exits(
        d,
        index_transfer_signals(d),
        costs,
        sl_atr=None,
        tp_r=None,
        time_stop_bars=None,
        flatten_min=INDEX_FLAT_MIN,
        flatten_clock="et",
        flatten_reason="flat_1545",
    )
    gold = simulate_exits(
        d,
        gold_transfer_signals(d),
        costs,
        sl_atr=1.0,
        tp_r=1.0,
        time_stop_bars=6,
        flatten_min=GOLD_FLAT_MIN_ET,
        flatten_clock="et",
        flatten_reason="flat_1100",
    )
    btc = simulate_exits(
        d,
        btc_transfer_signals(d),
        costs,
        sl_atr=1.0,
        tp_r=1.0,
        time_stop_bars=6,
        flatten_min=NY_FLAT_MIN,
        flatten_clock="et",
        flatten_reason="flat_1130",
    )
    fx = simulate_exits(
        d,
        eurusd_mr_transfer_signals(d),
        costs,
        sl_atr=1.0,
        tp_r=1.0,
        time_stop_bars=6,
        flatten_min=EURUSD_FLAT_MIN,
        flatten_clock="et",
        flatten_reason="flat_1645",
    )
    return {
        "index_transfer": {
            "family_id": "index_transfer",
            "role": "transfer_never_ranked",
            **pack_slices(idx, hs),
        },
        "gold_transfer": {
            "family_id": "gold_transfer",
            "role": "transfer_never_ranked",
            **pack_slices(gold, hs),
        },
        "btc_transfer": {
            "family_id": "btc_transfer",
            "role": "transfer_never_ranked",
            **pack_slices(btc, hs),
        },
        "eurusd_mr_transfer": {
            "family_id": "eurusd_mr_transfer",
            "role": "transfer_never_ranked",
            **pack_slices(fx, hs),
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="oil session scalp replay / transfers")
    p.add_argument("--lock", type=Path, default=LOCK_PATH)
    p.add_argument("--csv", type=Path, default=None)
    p.add_argument("--mode", choices=("transfers", "family", "all"), default="transfers")
    p.add_argument("--family", default=FAM_LONDON)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    lock = load_lock(args.lock)
    costs = costs_from_lock(lock)
    require_oil_cost_book(lock, costs)
    csv = args.csv or (_ROOT / lock["data"]["path"])
    d = load_oil_m5(csv, expected_sha256=lock["data"]["sha256"])
    report: dict = {
        "search_id": lock["search_id"],
        "promote": False,
        "live_go": False,
        "holdout_start": lock["holdout"]["start"],
        "bars": len(d),
        "costs": costs.__dict__,
    }
    if args.mode in ("transfers", "all"):
        report["transfers"] = run_transfers(d, lock, costs)
    if args.mode in ("family", "all"):
        g = lock["grid"]
        fam, _tr = run_family(
            d,
            lock,
            costs,
            args.family,
            sl_atr=float(g["sl_atr"][0]),
            tp_r=float(g["tp_r"][0]),
            time_stop_bars=int(g["time_stop_bars"][0]),
            min_atr_pct=float(g["min_atr_pct"][0]),
            eia_blackout=False,
        )
        report["family"] = {k: v for k, v in fam.items() if k != "trades"}
    if args.out:
        write_slim_json(args.out, report)
        print("wrote", args.out)
    print(json.dumps({k: report[k] for k in report if k != "transfers"}, indent=2)[:2000])
    if "transfers" in report:
        for name, block in report["transfers"].items():
            print(name, "develop PF", block["develop"]["profit_factor"], "n", block["develop"]["trades"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
