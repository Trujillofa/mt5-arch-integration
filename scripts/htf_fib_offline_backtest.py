#!/usr/bin/env python3
"""Offline approximation of ForexHtfPivotsFib signals + ATR exits.

This is a research surrogate for MT5 Strategy Tester when Wine headless tester
is unreliable. Logic mirrors the indicator defaults (INTRADAY-style):
  - Confirmed pivots on H4 (from H1 bars, left=right=5)
  - Directional Fib golden zone 61.8–78.6
  - EMA 20/50 timing + EMA 200 bias
  - RSI(14) zone + RSI SMA(14) filter
  - Entry on closed H1 bar; SL=1.5*ATR, TP=2.0*ATR; one position; reverse on flip

Usage:
  python3 scripts/htf_fib_offline_backtest.py \\
    --csv /path/to/eurusd_h1.csv \\
    --from 2024-06-01 --to 2025-01-01
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Allow `python3 scripts/htf_fib_offline_backtest.py` to find htf_fib_core
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


# Causal pivot/fib helpers (stamp at c+right, not pivot center c)
from htf_fib_core import (  # noqa: E402
    confirmed_pivots,
    expand_fib_states,
    fib_level,
    walk_swing_and_fibs,
)


@dataclass
class Trade:
    side: int
    entry_i: int
    entry: float
    sl: float
    tp: float
    exit_i: int | None = None
    exit: float | None = None
    reason: str = ""


def run_backtest(
    df: pd.DataFrame,
    left: int = 5,
    right: int = 5,
    *,
    use_rsi_ma_filter: bool = True,
    rsi_long_max: float = 35.0,
    rsi_short_min: float = 65.0,
) -> dict:
    df = df.copy()
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi"] = rsi(df["close"], 14)
    df["rsi_ma"] = sma(df["rsi"], 14)
    df["atr"] = atr(df, 14)

    # Build H4 bars from H1
    h4 = (
        df.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        .dropna()
    )
    events = confirmed_pivots(h4["high"].values, h4["low"].values, left, right)
    # map H4 index -> timestamp
    h4_times = h4.index.to_list()
    events_ts = [(h4_times[i], price, t) for i, price, t in events if i < len(h4_times)]

    # Convert events to H1 integer indices via searchsorted
    h1_index = df.index
    events_h1 = []
    for ts, price, t in events_ts:
        # pivot bar end ≈ ts (left edge of H4); use asof
        pos = h1_index.searchsorted(ts, side="right") - 1
        if pos >= 0:
            events_h1.append((pos, price, t))

    states = walk_swing_and_fibs(events_h1)
    # expand state to each bar: fib active only after confirmation idx (c+right)
    n = len(df)
    direction, f618, f786 = expand_fib_states(n, states)

    close = df["close"].values
    ema200 = df["ema200"].values
    r = df["rsi"].values
    rma = df["rsi_ma"].values
    atr_v = df["atr"].values
    high = df["high"].values
    low = df["low"].values

    signal = np.zeros(n, dtype=int)
    for i in range(1, n):
        if np.isnan(f618[i]) or direction[i] == 0 or np.isnan(r[i]) or np.isnan(rma[i]):
            continue
        c = close[i]
        lo_z, hi_z = min(f618[i], f786[i]), max(f618[i], f786[i])
        in_zone = lo_z <= c <= hi_z
        if not in_zone:
            continue
        rsi_long_ok = r[i] <= rsi_long_max
        rsi_short_ok = r[i] >= rsi_short_min
        if use_rsi_ma_filter:
            if not (r[i] > rma[i]):
                rsi_long_ok = False
            if not (r[i] < rma[i]):
                rsi_short_ok = False

        if direction[i] == 1 and c > ema200[i] and rsi_long_ok:
            c1 = close[i - 1]
            prev_ok = r[i - 1] <= rsi_long_max
            if use_rsi_ma_filter:
                prev_ok = prev_ok and (r[i - 1] > rma[i - 1])
            prev = (
                direction[i] == 1
                and min(f618[i], f786[i]) <= c1 <= max(f618[i], f786[i])
                and c1 > ema200[i - 1]
                and prev_ok
            )
            if not prev:
                signal[i] = 1
        elif direction[i] == -1 and c < ema200[i] and rsi_short_ok:
            c1 = close[i - 1]
            prev_ok = r[i - 1] >= rsi_short_min
            if use_rsi_ma_filter:
                prev_ok = prev_ok and (r[i - 1] < rma[i - 1])
            prev = (
                direction[i] == -1
                and min(f618[i], f786[i]) <= c1 <= max(f618[i], f786[i])
                and c1 < ema200[i - 1]
                and prev_ok
            )
            if not prev:
                signal[i] = -1

    # Trade simulation
    trades: list[Trade] = []
    pos: Trade | None = None
    sl_m, tp_m = 1.5, 2.0

    for i in range(n):
        if pos is not None:
            hit = False
            if pos.side == 1:
                if low[i] <= pos.sl:
                    pos.exit_i, pos.exit, pos.reason = i, pos.sl, "sl"
                    hit = True
                elif high[i] >= pos.tp:
                    pos.exit_i, pos.exit, pos.reason = i, pos.tp, "tp"
                    hit = True
            else:
                if high[i] >= pos.sl:
                    pos.exit_i, pos.exit, pos.reason = i, pos.sl, "sl"
                    hit = True
                elif low[i] <= pos.tp:
                    pos.exit_i, pos.exit, pos.reason = i, pos.tp, "tp"
                    hit = True
            if hit:
                trades.append(pos)
                pos = None

        s = int(signal[i])
        if s == 0 or np.isnan(atr_v[i]) or atr_v[i] <= 0:
            continue
        # enter next bar open ≈ this close for simplicity
        if pos is not None:
            if pos.side == s:
                continue
            # reverse
            pos.exit_i, pos.exit, pos.reason = i, close[i], "reverse"
            trades.append(pos)
            pos = None

        entry = close[i]
        dist_sl = atr_v[i] * sl_m
        dist_tp = atr_v[i] * tp_m
        if s > 0:
            pos = Trade(1, i, entry, entry - dist_sl, entry + dist_tp)
        else:
            pos = Trade(-1, i, entry, entry + dist_sl, entry - dist_tp)

    if pos is not None:
        pos.exit_i, pos.exit, pos.reason = n - 1, close[-1], "eod"
        trades.append(pos)

    # PnL in R (risk units) and crude $ (1 lot ≈ $10/pip for EURUSD; use price pnl * 100000 for 1 lot)
    contract = 100_000.0
    lots = 0.10
    pnls = []
    for t in trades:
        if t.exit is None:
            continue
        raw = (t.exit - t.entry) * t.side * contract * lots
        pnls.append(raw)

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = -sum(losses) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    equity = np.cumsum(pnls) if pnls else np.array([0.0])
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else 0.0

    return {
        "bars": n,
        "signals": int((signal != 0).sum()),
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(pnls)) if pnls else 0.0,
        "net_pnl_usd_0.1lot": float(sum(pnls)),
        "profit_factor": float(pf) if pf != float("inf") else None,
        "max_dd_usd_0.1lot": max_dd,
        "avg_trade_usd": float(np.mean(pnls)) if pnls else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--from", dest="date_from", default="2024-06-01")
    ap.add_argument("--to", dest="date_to", default="2025-01-01")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--no-rsi-ma-filter",
        action="store_true",
        help="Disable RSI>MA / RSI<MA filter (matches InpUseRsiMaFilter=false)",
    )
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    if "timestamp" in df.columns:
        # ms epoch
        ts = df["timestamp"]
        if ts.iloc[0] > 1e12:
            df["time"] = pd.to_datetime(ts, unit="ms", utc=True)
        else:
            df["time"] = pd.to_datetime(ts, unit="s", utc=True)
        df = df.set_index("time").sort_index()
    else:
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], utc=True)
        df = df.set_index(df.columns[0]).sort_index()

    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.loc[args.date_from : args.date_to]

    use_filter = not args.no_rsi_ma_filter
    stats = run_backtest(df, use_rsi_ma_filter=use_filter)
    stats["symbol"] = "EURUSD"
    stats["period"] = "H1"
    stats["from"] = args.date_from
    stats["to"] = args.date_to
    stats["use_rsi_ma_filter"] = use_filter
    stats["note"] = (
        "Offline approximation of HTF Fib (H4 pivots from H1). "
        "Pivots stamped at confirmation bar c+right (causal). "
        "Not identical to MT5 iCustom; use ForexHtfFibTester in Strategy Tester for platform parity."
    )
    text = json.dumps(stats, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
