#!/usr/bin/env python3
"""Replay gold session-scalp rules on MT5 caches / xauusd_data.csv.

Baseline
--------
Unmodified ``ny_cash_orb_vwap_ema_flat`` (US cash 09:30 OR, flatten 15:45 ET)
on gold OHLC with the gold cost book. This is the "swap the symbol" control.

Adjusted (frozen, not a search)
-------------------------------
``xau_london_orb_overlap_vwap_ema_flat``: London 30m OR, London VWAP, EMA 9/21,
London + NY-metals entry boxes, ATR SL/TP, flatten at the box end.

Costs (required; a zero-cost run is unfalsifiable)
--------------------------------------------------
Round-trip charged once at the fill bar, same shape as ``backtest.simulate``:

    (spread_pts + 2 * slippage_points) * point * contract * lots
    + 2 * commission_per_lot * lots

Gold book: point 0.01, contract 100, 1 lot, Standard-STP commission 0,
slippage 10 MT5 points (explicit unmeasured assumption; not a claim of
zero slip). Hostile-spread skip at 40 points.

Holdout
-------
``HOLDOUT_START = 2026-01-01`` from ``results/xau_holdout_lock.json``.
This script does not search. Candidates are frozen in ``CANDIDATES``.
Holdout is evaluation-only. Do not write ``strategy_params.json``.

SAFETY: offline research only. promote / live_go = no. Never ``--live``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_backtest import (  # noqa: E402, I001
    CostSpec as IndexCostSpec,
    infer_hc_tf,
    load_m5_csv,
    metrics_from_trades as index_metrics_from_trades,
    read_mt5_hc,
    simulate_flatten as index_simulate_flatten,
)
from us_index_session_core import scalp_signal_series as index_signal_series  # noqa: E402
from xau_session_scalp_core import (  # noqa: E402
    ATR_PERIOD,
    BASELINE_FAMILY_ID,
    SUPERSEDED_FAMILY_ID,
    MIN_ATR_PCT,
    OR_MINUTES,
    SessionBox,
    flatten_time_for_box,
    scalp_signal_series,
    session_box_at,
    to_et,
    to_utc,
    wilder_atr,
)

HOLDOUT_START = date(2026, 1, 1)
PROMOTE = False
LIVE_GO = False
POINT_SIZE = 0.01
CONTRACT_SIZE = 100.0
DEFAULT_LOTS = 1.0
DEFAULT_SLIPPAGE_POINTS = 10.0
DEFAULT_COMMISSION = 0.0
DEFAULT_MAX_SPREAD = 40.0
FAT_REPORT_KEYS = frozenset({"trades"})

PRIMARY_CANDIDATE = "london30_both_windows"
CANDIDATES: tuple[dict, ...] = (
    {
        "id": "london30_both_windows",
        "or_minutes": 30,
        "allow_ny": True,
        "or_buffer_atr_frac": 0.10,
        "sl_atr": 1.0,
        "tp_atr": 1.2,
    },
    {
        "id": "london30_london_only",
        "or_minutes": 30,
        "allow_ny": False,
        "or_buffer_atr_frac": 0.10,
        "sl_atr": 1.0,
        "tp_atr": 1.2,
    },
    {
        "id": "london15_london_only",
        "or_minutes": 15,
        "allow_ny": False,
        "or_buffer_atr_frac": 0.10,
        "sl_atr": 1.0,
        "tp_atr": 1.2,
    },
)


@dataclass(frozen=True)
class CostSpec:
    point_size: float = POINT_SIZE
    contract_size: float = CONTRACT_SIZE
    lots: float = DEFAULT_LOTS
    commission_per_lot: float = DEFAULT_COMMISSION
    slippage_points: float = DEFAULT_SLIPPAGE_POINTS
    max_spread_points: float = DEFAULT_MAX_SPREAD


@dataclass
class Trade:
    side: int
    signal_i: int
    fill_i: int
    exit_i: int
    entry: float
    exit: float
    reason: str
    box: str
    utc_date: str
    signal_time: str
    fill_time: str
    exit_time: str
    spread_pts: float
    cost: float
    pnl: float
    mae: float
    mfe: float


def gold_cost_book(**overrides: float) -> CostSpec:
    kw = {
        "point_size": POINT_SIZE,
        "contract_size": CONTRACT_SIZE,
        "lots": DEFAULT_LOTS,
        "commission_per_lot": DEFAULT_COMMISSION,
        "slippage_points": DEFAULT_SLIPPAGE_POINTS,
        "max_spread_points": DEFAULT_MAX_SPREAD,
    }
    kw.update(overrides)
    return CostSpec(**kw)


def refuse_frictionless(costs: CostSpec) -> CostSpec:
    if float(costs.slippage_points) <= 0.0 and float(costs.commission_per_lot) <= 0.0:
        # Spread-from-bars still applies; slip=0 is the unmeasured XAU-loop
        # default and is refused here so this track cannot ship frictionless.
        raise SystemExit(
            "gold scalp book requires slippage_points > 0 "
            "(unmeasured but explicit; do not ship a zero-slip run)"
        )
    if float(costs.contract_size) != CONTRACT_SIZE:
        raise SystemExit(f"gold contract_size must be {CONTRACT_SIZE:g}")
    if float(costs.point_size) != POINT_SIZE:
        raise SystemExit(f"gold point_size must be {POINT_SIZE:g}")
    return costs


def _round_trip_cost(spread_pts: float, costs: CostSpec) -> float:
    return (
        (spread_pts + 2.0 * costs.slippage_points)
        * costs.point_size
        * costs.contract_size
        * costs.lots
        + 2.0 * costs.commission_per_lot * costs.lots
    )


def _flatten_index(
    times: list[datetime], start: int, box: SessionBox
) -> int | None:
    deadline = flatten_time_for_box(times[start], box)
    for j in range(start, len(times)):
        if to_utc(times[j]) >= to_utc(deadline):
            return j
        # session calendar rolled — flatten last bar of the box day
        if box == SessionBox.LONDON:
            if times[j].astimezone(deadline.tzinfo).date() != deadline.date():
                return j - 1 if j > start else None
        else:
            if to_et(times[j]).date() != to_et(times[start]).date():
                return j - 1 if j > start else None
    return len(times) - 1


def simulate_scalp(
    times: list[datetime],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    signals: np.ndarray,
    costs: CostSpec,
    *,
    atr: np.ndarray | None = None,
    sl_atr: float = 1.0,
    tp_atr: float = 1.2,
    allow_ny: bool = True,
    or_minutes: int = OR_MINUTES,
) -> list[Trade]:
    """Next-bar open fill; ATR SL/TP; flatten at the session-box end."""
    n = len(times)
    if atr is None:
        atr = wilder_atr(high, low, close, ATR_PERIOD)
    trades: list[Trade] = []
    i = 0
    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue
        box = session_box_at(times[i], or_minutes=or_minutes, allow_ny=allow_ny)
        if box == SessionBox.NONE:
            i += 1
            continue
        fill_i = i + 1
        if fill_i >= n:
            break
        spr = float(spread[fill_i]) if np.isfinite(spread[fill_i]) else 0.0
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            i += 1
            continue
        exit_i = _flatten_index(times, fill_i, box)
        if exit_i is None or exit_i <= fill_i:
            i += 1
            continue
        entry = float(open_[fill_i])
        atr_i = float(atr[i]) if np.isfinite(atr[i]) else 0.0
        sl = entry - sig * sl_atr * atr_i if atr_i > 0 and sl_atr > 0 else None
        tp = entry + sig * tp_atr * atr_i if atr_i > 0 and tp_atr > 0 else None
        reason = "flatten_session"
        exit_px = float(open_[exit_i])
        hit_i = exit_i
        for j in range(fill_i, exit_i + 1):
            hit_sl = False
            hit_tp = False
            if sl is not None:
                hit_sl = (float(low[j]) <= sl) if sig > 0 else (float(high[j]) >= sl)
            if tp is not None:
                hit_tp = (float(high[j]) >= tp) if sig > 0 else (float(low[j]) <= tp)
            if hit_sl and hit_tp:
                exit_px = float(sl)
                reason = "sl_tp_same_bar"
                hit_i = j
                break
            if hit_sl:
                exit_px = float(sl)
                reason = "sl"
                hit_i = j
                break
            if hit_tp:
                exit_px = float(tp)
                reason = "tp"
                hit_i = j
                break
        cost = _round_trip_cost(spr, costs)
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        window_h = high[fill_i : hit_i + 1]
        window_l = low[fill_i : hit_i + 1]
        if sig > 0:
            mae = float(entry - np.min(window_l)) if len(window_l) else 0.0
            mfe = float(np.max(window_h) - entry) if len(window_h) else 0.0
        else:
            mae = float(np.max(window_h) - entry) if len(window_h) else 0.0
            mfe = float(entry - np.min(window_l)) if len(window_l) else 0.0
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill_i,
                exit_i=hit_i,
                entry=entry,
                exit=exit_px,
                reason=reason,
                box=box.name,
                utc_date=str(to_utc(times[fill_i]).date()),
                signal_time=to_utc(times[i]).isoformat(),
                fill_time=to_utc(times[fill_i]).isoformat(),
                exit_time=to_utc(times[hit_i]).isoformat(),
                spread_pts=spr,
                cost=cost,
                pnl=pnl,
                mae=mae,
                mfe=mfe,
            )
        )
        i = hit_i + 1
    return trades


def metrics_from_trades(trades: list[Trade]) -> dict:
    # Reuse the index metric shape via a thin adapter.
    class _T:
        def __init__(self, t: Trade) -> None:
            self.pnl = t.pnl
            self.side = t.side
            self.mae = t.mae
            self.mfe = t.mfe

    return index_metrics_from_trades([_T(t) for t in trades])  # type: ignore[arg-type]


def split_by_holdout(
    trades: list[Trade], holdout_start: date = HOLDOUT_START
) -> tuple[list[Trade], list[Trade]]:
    pre = [t for t in trades if date.fromisoformat(t.utc_date) < holdout_start]
    post = [t for t in trades if date.fromisoformat(t.utc_date) >= holdout_start]
    return pre, post


def slim_committed_report(report: dict) -> dict:
    return {k: v for k, v in report.items() if k not in FAT_REPORT_KEYS}


def write_slim_json(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(slim_committed_report(report), indent=2) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_bars(
    *,
    hc: Path | None = None,
    csv: Path | None = None,
    timeframe: str | None = None,
    server_utc_offset_sec: int = 0,
) -> tuple[pd.DataFrame, dict]:
    meta: dict = {
        "server_utc_offset_sec": int(server_utc_offset_sec),
        "source": "",
        "timeframe": timeframe or "",
    }
    if hc is not None:
        raw = read_mt5_hc(Path(hc))
        tf = infer_hc_tf(raw["server_epoch"].to_numpy())
        server = pd.to_datetime(raw["server_epoch"], unit="s", utc=True)
        utc = server - pd.to_timedelta(int(server_utc_offset_sec), unit="s")
        df = raw.copy()
        df["time_utc"] = utc
        df["time_server"] = server
        meta["source"] = str(hc)
        meta["timeframe"] = tf
        meta["sha256"] = sha256_file(Path(hc))
        return df.sort_values("time_utc").reset_index(drop=True), meta
    if csv is None:
        raise SystemExit("provide --hc or --csv")
    path = Path(csv)
    raw = pd.read_csv(path)
    if "timeframe" in raw.columns and timeframe:
        raw = raw.loc[raw["timeframe"].astype(str) == timeframe].copy()
    if "time_utc" in raw.columns:
        df = load_m5_csv(path, server_utc_offset_sec)
    else:
        tcol = "time" if "time" in raw.columns else raw.columns[0]
        utc = pd.to_datetime(raw[tcol], utc=True, errors="coerce")
        df = raw.copy()
        df["time_utc"] = utc
        for col in ("open", "high", "low", "close", "tick_volume", "spread"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "tick_volume" not in df.columns:
            df["tick_volume"] = 1.0
        if "spread" not in df.columns:
            df["spread"] = 0.0
        df = df.dropna(subset=["open", "high", "low", "close", "time_utc"])
        df = df.sort_values("time_utc").reset_index(drop=True)
    meta["source"] = str(path)
    meta["timeframe"] = timeframe or meta.get("timeframe") or "CSV"
    meta["sha256"] = sha256_file(path)
    return df, meta


def _arrays(df: pd.DataFrame) -> tuple:
    times = [to_utc(ts.to_pydatetime()) for ts in df["time_utc"]]
    return (
        times,
        df["open"].to_numpy(float),
        df["high"].to_numpy(float),
        df["low"].to_numpy(float),
        df["close"].to_numpy(float),
        df["tick_volume"].to_numpy(float),
        df["spread"].to_numpy(float),
    )


def data_block(df: pd.DataFrame, meta: dict) -> dict:
    t0 = df["time_utc"].iloc[0] if len(df) else ""
    t1 = df["time_utc"].iloc[-1] if len(df) else ""
    return {
        "source": meta.get("source"),
        "timeframe": meta.get("timeframe"),
        "sha256": meta.get("sha256"),
        "bars": int(len(df)),
        "start": str(t0),
        "end": str(t1),
        "selection_cutoff": str(HOLDOUT_START),
        "holdout_sealed": True,
        "server_utc_offset_sec": meta.get("server_utc_offset_sec"),
    }


def run_baseline(df: pd.DataFrame, meta: dict, costs: CostSpec) -> dict:
    times, open_, high, low, close, vol, spread = _arrays(df)
    signals = index_signal_series(times, high, low, close, vol)
    idx_costs = IndexCostSpec(
        point_size=costs.point_size,
        contract_size=costs.contract_size,
        lots=costs.lots,
        commission_per_lot=costs.commission_per_lot,
        slippage_points=costs.slippage_points,
        max_spread_points=costs.max_spread_points,
    )
    trades_raw = index_simulate_flatten(
        times, open_, high, low, close, spread, signals, idx_costs
    )
    trades = [
        Trade(
            side=t.side,
            signal_i=t.signal_i,
            fill_i=t.fill_i,
            exit_i=t.exit_i,
            entry=t.entry,
            exit=t.exit,
            reason=t.reason,
            box="NY_CASH",
            utc_date=str(to_utc(times[t.fill_i]).date()),
            signal_time=t.signal_time,
            fill_time=t.fill_time,
            exit_time=t.exit_time,
            spread_pts=t.spread_pts,
            cost=t.cost,
            pnl=t.pnl,
            mae=t.mae,
            mfe=t.mfe,
        )
        for t in trades_raw
    ]
    pre, post = split_by_holdout(trades)
    return {
        "family_id": BASELINE_FAMILY_ID,
        "role": "baseline_unmodified_index_rules_on_gold",
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "holdout_start": str(HOLDOUT_START),
        "costs": asdict(costs),
        "exit": "flatten_1545_ET_next_bar_open_fill",
        "data": data_block(df, meta),
        "signals": int(np.count_nonzero(signals)),
        "all": metrics_from_trades(trades),
        "develop": metrics_from_trades(pre),
        "holdout": metrics_from_trades(post),
        "note": (
            "Unmodified NY-cash 09:30 ORB+VWAP+EMA on gold. "
            "Holdout is evaluation-only. Not a develop screen."
        ),
        "trades": [asdict(t) for t in trades],
    }


def run_adjusted(
    df: pd.DataFrame,
    meta: dict,
    costs: CostSpec,
    *,
    candidate: dict | None = None,
) -> dict:
    cfg = dict(CANDIDATES[0] if candidate is None else candidate)
    times, open_, high, low, close, vol, spread = _arrays(df)
    signals = scalp_signal_series(
        times,
        high,
        low,
        close,
        vol,
        or_minutes=int(cfg["or_minutes"]),
        min_atr_pct=MIN_ATR_PCT,
        or_buffer_atr_frac=float(cfg["or_buffer_atr_frac"]),
        allow_ny=bool(cfg["allow_ny"]),
    )
    atr = wilder_atr(high, low, close, ATR_PERIOD)
    trades = simulate_scalp(
        times,
        open_,
        high,
        low,
        close,
        spread,
        signals,
        costs,
        atr=atr,
        sl_atr=float(cfg["sl_atr"]),
        tp_atr=float(cfg["tp_atr"]),
        allow_ny=bool(cfg["allow_ny"]),
        or_minutes=int(cfg["or_minutes"]),
    )
    pre, post = split_by_holdout(trades)
    return {
        "family_id": SUPERSEDED_FAMILY_ID,
        "candidate_id": cfg["id"],
        "role": "adjusted_gold_rules",
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "holdout_start": str(HOLDOUT_START),
        "params": {
            "or_minutes": cfg["or_minutes"],
            "allow_ny": cfg["allow_ny"],
            "or_buffer_atr_frac": cfg["or_buffer_atr_frac"],
            "sl_atr": cfg["sl_atr"],
            "tp_atr": cfg["tp_atr"],
            "min_atr_pct": MIN_ATR_PCT,
            "ema_fast": 9,
            "ema_slow": 21,
        },
        "costs": asdict(costs),
        "exit": "atr_sl_tp_then_session_box_flatten_next_bar_open_fill",
        "data": data_block(df, meta),
        "signals": int(np.count_nonzero(signals)),
        "all": metrics_from_trades(trades),
        "develop": metrics_from_trades(pre),
        "holdout": metrics_from_trades(post),
        "note": (
            "Frozen gold combo. Candidates were declared before metrics. "
            "Holdout is evaluation-only. Not permission to --live."
        ),
        "trades": [asdict(t) for t in trades],
    }


def default_fp_m5() -> Path:
    return Path.home() / (
        ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/"
        "Bases/FPMarketsSC-Live/history/XAUUSD.r/cache/M5.hc"
    )


def default_vantage_m15() -> Path:
    return Path.home() / (
        ".mt5-vantage/drive_c/Program Files/Vantage International MT5/"
        "Bases/VantageMarkets-Live 5/history/XAUUSD/cache/M15.hc"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hc", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--timeframe", default=None)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--server-utc-offset", type=int, default=0)
    ap.add_argument(
        "--mode",
        choices=("baseline", "adjusted", "candidates", "all"),
        default="all",
    )
    ap.add_argument("--out-dir", type=Path, default=_ROOT / "results" / "xau_session_scalp")
    ap.add_argument("--lots", type=float, default=DEFAULT_LOTS)
    ap.add_argument("--slippage-points", type=float, default=DEFAULT_SLIPPAGE_POINTS)
    ap.add_argument("--commission-per-lot", type=float, default=DEFAULT_COMMISSION)
    ap.add_argument("--max-spread-points", type=float, default=DEFAULT_MAX_SPREAD)
    args = ap.parse_args()
    costs = refuse_frictionless(
        gold_cost_book(
            lots=args.lots,
            slippage_points=args.slippage_points,
            commission_per_lot=args.commission_per_lot,
            max_spread_points=args.max_spread_points,
        )
    )
    hc = args.hc
    csv = args.csv
    if hc is None and csv is None:
        if default_fp_m5().is_file():
            hc = default_fp_m5()
        else:
            csv = _ROOT / "xauusd_data.csv"
            args.timeframe = args.timeframe or "M15"
    df, meta = load_bars(
        hc=hc,
        csv=csv,
        timeframe=args.timeframe,
        server_utc_offset_sec=args.server_utc_offset,
    )
    meta["symbol"] = args.symbol
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.mode in ("baseline", "all"):
        base = run_baseline(df, meta, costs)
        write_slim_json(out_dir / "baseline.json", base)
        print(json.dumps(slim_committed_report(base), indent=2))
        print(f"wrote {out_dir / 'baseline.json'}")

    if args.mode in ("adjusted", "all"):
        primary = next(c for c in CANDIDATES if c["id"] == PRIMARY_CANDIDATE)
        adj = run_adjusted(df, meta, costs, candidate=primary)
        write_slim_json(out_dir / "adjusted.json", adj)
        print(json.dumps(slim_committed_report(adj), indent=2))
        print(f"wrote {out_dir / 'adjusted.json'}")

    if args.mode in ("candidates", "all"):
        rows = []
        for cand in CANDIDATES:
            rep = run_adjusted(df, meta, costs, candidate=cand)
            rows.append(
                {
                    "id": cand["id"],
                    "params": rep["params"],
                    "develop": rep["develop"],
                    "holdout_evaluated": cand["id"] == PRIMARY_CANDIDATE,
                    "holdout": (
                        rep["holdout"] if cand["id"] == PRIMARY_CANDIDATE else None
                    ),
                }
            )
        pack = {
            "family_id": SUPERSEDED_FAMILY_ID,
            "primary": PRIMARY_CANDIDATE,
            "selection": (
                "none — primary was frozen a priori; "
                "alternates are develop-only sensitivity"
            ),
            "promote": PROMOTE,
            "live_go": LIVE_GO,
            "holdout_start": str(HOLDOUT_START),
            "costs": asdict(costs),
            "data": data_block(df, meta),
            "candidates": rows,
        }
        write_slim_json(out_dir / "candidates.json", pack)
        print(json.dumps(pack, indent=2))
        print(f"wrote {out_dir / 'candidates.json'}")


if __name__ == "__main__":
    main()
