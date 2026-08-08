#!/usr/bin/env python3
"""
Offline XAUUSD H1 backtest from xauusd_data.csv.
Prints Total Net Profit, Win Rate (%), Profit Factor, Max Drawdown (%).
Autonomous parameter search until gates: PF>1.5, WR>55%, MaxDD<10%.

Writing strategy_params.json is opt-in (``--save``): a plain run is read-only so
tests and exploratory runs never mutate tracked state. Saved params carry the
``data`` window they were fitted on, so the recorded metrics stay reproducible
after the CSV is extended (see ``slice_to_window``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

CSV_PATH = Path(__file__).resolve().parent / "xauusd_data.csv"
PARAMS_PATH = Path(__file__).resolve().parent / "strategy_params.json"
HOLDOUT_LOCK = Path(__file__).resolve().parent / "results" / "xau_holdout_lock.json"
START_BALANCE = 10_000.0
# $1 move on 1.0 lot ≈ $100 (100 oz); so $1 move on 0.01 lot ≈ $1
CONTRACT_SIZE = 100.0


@dataclass
class Metrics:
    net_profit: float
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    n_trades: int
    wins: int
    losses: int


def load_h1() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["time"])
    df = df.loc[df["timeframe"] == "H1"].sort_values("time").reset_index(drop=True)
    if df.empty:
        raise RuntimeError(f"No H1 data in {CSV_PATH}")
    return df


def holdout_start(lock_path: Path = HOLDOUT_LOCK) -> pd.Timestamp | None:
    """Pre-registered selection boundary from results/xau_holdout_lock.json.

    The protocol is `holdout_rule: NEVER used for selection`, so any search that
    picks params must stay strictly before this timestamp. Matches the develop
    convention used by scripts/xau_*.py: develop is ``time < holdout_start``.
    """
    if not lock_path.is_file():
        return None
    value = json.loads(lock_path.read_text()).get("holdout_start")
    if not value:
        return None
    ts = cast(pd.Timestamp, pd.Timestamp(value))
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def develop_only(raw: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    out = raw.loc[raw["time"] < cutoff].reset_index(drop=True)
    if out.empty:
        raise RuntimeError(f"No H1 bars before {cutoff}; nothing to fit on.")
    return out


def data_window(raw: pd.DataFrame, csv_path: Path = CSV_PATH) -> dict:
    """Fingerprint the exact bars a fit was performed on."""
    return {
        "csv": csv_path.name,
        "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest() if csv_path.is_file() else None,
        "timeframe": "H1",
        "bars": int(len(raw)),
        "start": raw["time"].iloc[0].isoformat(),
        "end": raw["time"].iloc[-1].isoformat(),
    }


def slice_to_window(raw: pd.DataFrame, window: dict) -> pd.DataFrame:
    """Restrict raw H1 bars to a recorded fit window.

    Replaying params over the whole CSV silently changes the result once the CSV
    is extended; slicing back to the recorded window is what makes the metrics in
    strategy_params.json checkable. Raises if the window is no longer covered.
    """
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    out = raw.loc[(raw["time"] >= start) & (raw["time"] <= end)].reset_index(drop=True)
    if len(out) != window["bars"]:
        raise RuntimeError(
            f"fit window {start} → {end} has {len(out)} bars in {CSV_PATH.name}, "
            f"but was fitted on {window['bars']}. The CSV changed inside the window; "
            "re-fit with `python3 backtest.py --save`."
        )
    return out


def normalize_params(params: dict) -> dict:
    """JSON round-trip turns the `hours` tuple into a list; simulate() needs it back."""
    p = dict(params)
    hours = p.get("hours")
    p["hours"] = tuple(hours) if isinstance(hours, list) else hours
    return p


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["close"].astype(float)
    h = d["high"].astype(float)
    l = d["low"].astype(float)
    d["ema20"] = c.ewm(span=20, adjust=False).mean()
    d["ema50"] = c.ewm(span=50, adjust=False).mean()
    d["ema100"] = c.ewm(span=100, adjust=False).mean()
    d["ema200"] = c.ewm(span=200, adjust=False).mean()
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    d["bb_mid"] = mid
    d["bb_up"] = mid + 2.0 * sd
    d["bb_lo"] = mid - 2.0 * sd
    d["bb_lo15"] = mid - 1.5 * sd
    d["bb_lo25"] = mid - 2.5 * sd
    # MACD
    ef = c.ewm(span=12, adjust=False).mean()
    es = c.ewm(span=26, adjust=False).mean()
    d["macd"] = ef - es
    d["macd_sig"] = d["macd"].ewm(span=9, adjust=False).mean()
    d["macd_hist"] = d["macd"] - d["macd_sig"]
    d["hour"] = pd.to_datetime(d["time"], utc=True).dt.hour
    return d


def metrics_from_pnls(pnls: list[float], equity: np.ndarray) -> Metrics:
    if not pnls:
        return Metrics(0.0, 0.0, 0.0, 0.0, 0, 0, 0)
    a = np.asarray(pnls, dtype=float)
    wins = a[a > 0]
    losses = a[a <= 0]
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float(-losses.sum()) if len(losses) else 0.0
    pf = (gw / gl) if gl > 1e-12 else (99.0 if gw > 0 else 0.0)
    wr = 100.0 * len(wins) / len(a)
    peak = np.maximum.accumulate(equity)
    dd = np.where(peak > 0, (peak - equity) / peak, 0.0)
    return Metrics(
        net_profit=float(a.sum()),
        win_rate=float(wr),
        profit_factor=float(pf),
        max_drawdown_pct=float(dd.max() * 100),
        n_trades=len(a),
        wins=int(len(wins)),
        losses=int(len(losses)),
    )


def simulate(
    d: pd.DataFrame,
    *,
    mode: str = "bb_rsi",
    rsi_buy: float = 35.0,
    rsi_sell: float = 60.0,
    sl_atr: float = 1.5,
    tp_atr: float = 2.0,
    risk_pct: float = 0.01,
    max_lots: float = 0.5,
    bb_col: str = "bb_lo",
    require_uptrend: bool = True,
    trend_col: str = "ema100",
    use_macd_filter: bool = False,
    hours: tuple[int, ...] | None = None,
    cooldown: int = 2,
    long_only: bool = True,
    spread_col: str | None = None,
    point_size: float = 0.01,
    commission_per_lot: float = 0.0,
    slippage_points: float = 0.0,
) -> Metrics:
    """Bar loop simulator with OHLC stop/target and RSI soft exit.

    Costs default to zero, i.e. frictionless — the historical behaviour. Pass
    ``spread_col`` (per-bar spread in points, from MqlRates.spread) plus
    ``commission_per_lot``/``slippage_points`` to charge realistic costs; each
    closed trade is debited the round trip once, priced off its entry bar.
    """
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    rsi = d["rsi"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    bb_lo = d[bb_col].to_numpy(float)
    bb_mid = d["bb_mid"].to_numpy(float)
    bb_up = d["bb_up"].to_numpy(float)
    trend = d[trend_col].to_numpy(float)
    macd_h = d["macd_hist"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    if spread_col is not None and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    bal = START_BALANCE
    eq = np.zeros(n)
    pnls: list[float] = []
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    cool = 0
    warmup = 220

    for i in range(n):
        px = close[i]
        floating = bal + ((px - entry) * CONTRACT_SIZE * lots * pos if pos else 0.0)
        eq[i] = floating

        if pos != 0 and i >= 1 and not np.isnan(atr[i]):
            exit_px = None
            if pos > 0:
                if low[i] <= sl:
                    exit_px = sl
                elif high[i] >= tp:
                    exit_px = tp
                elif not np.isnan(rsi[i]) and rsi[i] >= rsi_sell:
                    exit_px = px
            else:
                if high[i] >= sl:
                    exit_px = sl
                elif low[i] <= tp:
                    exit_px = tp
                elif not np.isnan(rsi[i]) and rsi[i] <= (100 - rsi_sell):
                    exit_px = px
            if exit_px is not None:
                pnl = (exit_px - entry) * CONTRACT_SIZE * lots * pos - trade_cost
                bal += pnl
                pnls.append(pnl)
                pos = 0
                lots = 0.0
                trade_cost = 0.0
                cool = cooldown
                eq[i] = bal

        if cool > 0:
            cool -= 1
            continue
        if pos != 0 or i < warmup:
            continue
        if np.isnan(atr[i]) or np.isnan(rsi[i]) or atr[i] <= 0:
            continue
        if hours is not None and hour[i] not in hours:
            continue

        uptrend = close[i] > trend[i]
        downtrend = close[i] < trend[i]
        if require_uptrend and not uptrend and long_only:
            continue
        if use_macd_filter and macd_h[i] < 0 and long_only:
            continue

        long_sig = False
        short_sig = False
        if mode == "bb_rsi":
            # reclaim lower band after dip + RSI not overbought
            long_sig = (
                uptrend
                and low[i] <= bb_lo[i]
                and close[i] > bb_lo[i]
                and close[i] < bb_mid[i]
                and rsi[i] <= rsi_buy + 10
            )
            if not long_only and downtrend:
                short_sig = (
                    high[i] >= bb_up[i]
                    and close[i] < bb_up[i]
                    and close[i] > bb_mid[i]
                    and rsi[i] >= (100 - rsi_buy - 10)
                )
        elif mode == "rsi_cross":
            if i < 1 or np.isnan(rsi[i - 1]):
                continue
            long_sig = uptrend and rsi[i - 1] < rsi_buy <= rsi[i]
            if not long_only:
                short_sig = downtrend and rsi[i - 1] > (100 - rsi_buy) >= rsi[i]
        elif mode == "macd_pullback":
            if i < 2:
                continue
            long_sig = (
                uptrend
                and macd_h[i - 1] < 0 <= macd_h[i]
                and rsi[i] < rsi_buy + 15
                and close[i] > d["ema20"].iloc[i]
            )
        else:
            continue

        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * sl_atr
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * risk_pct
        # Floor to 0.01 lot; never force min lot if it would exceed risk_cash
        raw = risk_cash / (stop_dist * CONTRACT_SIZE)
        lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
        lots = min(lots, max_lots)
        min_lot = 0.01
        min_lot_risk = stop_dist * CONTRACT_SIZE * min_lot
        if lots < min_lot or min_lot_risk > risk_cash + 1e-9:
            continue

        # Round trip charged once, priced off the entry bar: spread is crossed on
        # entry, slippage assumed on both fills, commission per lot per side.
        trade_cost = (
            (spread_pts[i] + 2.0 * slippage_points) * point_size * CONTRACT_SIZE * lots
            + 2.0 * commission_per_lot * lots
        )

        if long_sig:
            pos = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr[i] * tp_atr
        else:
            pos = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr[i] * tp_atr

    if pos != 0:
        pnl = (close[-1] - entry) * CONTRACT_SIZE * lots * pos - trade_cost
        bal += pnl
        pnls.append(pnl)
        eq[-1] = bal

    return metrics_from_pnls(pnls, eq)


"""Cost settings applied to every simulate() call in a search run.

Empty = frictionless (historical behaviour). main() fills it from the CLI and
records it in strategy_params.json so a replay charges the same costs.
"""
COSTS: dict = {}


def sim(d: pd.DataFrame, params: dict) -> Metrics:
    """simulate() with the run's cost settings folded in."""
    return simulate(d, **params, **COSTS)


def passes(m: Metrics) -> bool:
    return (
        m.n_trades >= 20
        and m.profit_factor > 1.5
        and m.win_rate > 55.0
        and m.max_drawdown_pct < 10.0
    )


def print_metrics(m: Metrics) -> None:
    print(f"Total Net Profit: {m.net_profit:.2f}")
    print(f"Win Rate (%): {m.win_rate:.2f}")
    print(f"Profit Factor: {m.profit_factor:.4f}")
    print(f"Max Drawdown (%): {m.max_drawdown_pct:.2f}")
    print(f"Trades: {m.n_trades} (W={m.wins} L={m.losses})")


def search(d: pd.DataFrame) -> tuple[dict, Metrics]:
    candidates: list[dict] = []
    for mode in ("bb_rsi", "rsi_cross", "macd_pullback"):
        for rsi_buy in (30, 32, 35, 38, 40, 42):
            for rsi_sell in (50, 55, 58, 62, 65):
                for sl_a in (1.0, 1.2, 1.5, 2.0):
                    for tp_a in (1.2, 1.5, 2.0, 2.5, 3.0):
                        if tp_a < sl_a * 0.85:
                            continue
                        for bb in ("bb_lo", "bb_lo15", "bb_lo25"):
                            for trend in ("ema100", "ema200", "ema50"):
                                for macd_f in (False, True):
                                    for hrs in (None, tuple(range(7, 17)), tuple(range(12, 21))):
                                        candidates.append(
                                            dict(
                                                mode=mode,
                                                rsi_buy=float(rsi_buy),
                                                rsi_sell=float(rsi_sell),
                                                sl_atr=float(sl_a),
                                                tp_atr=float(tp_a),
                                                bb_col=bb,
                                                trend_col=trend,
                                                use_macd_filter=macd_f,
                                                hours=hrs,
                                                long_only=True,
                                                risk_pct=0.01,
                                                cooldown=2,
                                            )
                                        )

    # deterministic subsample for speed (~1200 evals)
    rng = np.random.default_rng(42)
    if len(candidates) > 1200:
        pick = rng.choice(len(candidates), size=1200, replace=False)
        candidates = [candidates[i] for i in sorted(pick)]

    # seed high-priority configs
    seeds = [
        dict(mode="bb_rsi", rsi_buy=35, rsi_sell=58, sl_atr=1.2, tp_atr=2.0, bb_col="bb_lo", trend_col="ema100", use_macd_filter=False, hours=None, long_only=True, risk_pct=0.01, cooldown=2),
        dict(mode="bb_rsi", rsi_buy=32, rsi_sell=55, sl_atr=1.0, tp_atr=1.8, bb_col="bb_lo15", trend_col="ema100", use_macd_filter=True, hours=None, long_only=True, risk_pct=0.01, cooldown=1),
        dict(mode="rsi_cross", rsi_buy=30, rsi_sell=60, sl_atr=1.5, tp_atr=2.5, bb_col="bb_lo", trend_col="ema200", use_macd_filter=False, hours=tuple(range(7, 17)), long_only=True, risk_pct=0.01, cooldown=3),
        dict(mode="macd_pullback", rsi_buy=40, rsi_sell=60, sl_atr=1.2, tp_atr=2.4, bb_col="bb_lo", trend_col="ema100", use_macd_filter=False, hours=None, long_only=True, risk_pct=0.01, cooldown=2),
        dict(mode="bb_rsi", rsi_buy=38, rsi_sell=52, sl_atr=1.0, tp_atr=1.5, bb_col="bb_lo", trend_col="ema50", use_macd_filter=False, hours=None, long_only=True, risk_pct=0.008, cooldown=1),
    ]
    candidates = seeds + candidates

    best_p = candidates[0]
    best_m = Metrics(0, 0, 0, 100, 0, 0, 0)
    best_score = -1e18

    for i, p in enumerate(candidates):
        m = sim(d, p)
        score = 0.0
        if m.n_trades >= 20:
            score += 50
        if m.profit_factor > 1.5:
            score += 200 + m.profit_factor * 20
        else:
            score += m.profit_factor * 5
        if m.win_rate > 55:
            score += 200 + m.win_rate
        else:
            score += m.win_rate * 0.5
        if m.max_drawdown_pct < 10:
            score += 200 - m.max_drawdown_pct
        else:
            score -= m.max_drawdown_pct * 2
        score += m.net_profit / 50.0
        if score > best_score:
            best_score = score
            best_p, best_m = p, m
        if passes(m) and m.profit_factor >= 1.55 and m.n_trades >= 25:
            return p, m
        if (i + 1) % 200 == 0:
            print(f"... searched {i+1}/{len(candidates)} best_PF={best_m.profit_factor:.3f} WR={best_m.win_rate:.1f} DD={best_m.max_drawdown_pct:.1f} n={best_m.n_trades}")

    return best_p, best_m


def refine(d: pd.DataFrame, base: dict) -> tuple[dict, Metrics]:
    """Local neighborhood search around a promising config."""
    best_p, best_m = base, sim(d, base)
    neighbors = []
    for rsi_buy in np.linspace(max(20, base["rsi_buy"] - 6), min(48, base["rsi_buy"] + 6), 7):
        for rsi_sell in np.linspace(max(45, base["rsi_sell"] - 8), min(75, base["rsi_sell"] + 8), 7):
            for sl_a in (0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 1.8):
                for tp_a in (1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 3.0):
                    if tp_a < sl_a * 0.9:
                        continue
                    q = dict(base)
                    q["rsi_buy"] = float(rsi_buy)
                    q["rsi_sell"] = float(rsi_sell)
                    q["sl_atr"] = float(sl_a)
                    q["tp_atr"] = float(tp_a)
                    neighbors.append(q)
    # unique-ish subsample
    rng = np.random.default_rng(1)
    if len(neighbors) > 500:
        neighbors = [neighbors[i] for i in sorted(rng.choice(len(neighbors), 500, replace=False))]

    for p in neighbors:
        m = sim(d, p)
        better = False
        if passes(m) and not passes(best_m):
            better = True
        elif passes(m) and passes(best_m):
            better = m.profit_factor > best_m.profit_factor or (
                abs(m.profit_factor - best_m.profit_factor) < 0.05 and m.net_profit > best_m.net_profit
            )
        elif not passes(best_m):
            better = (
                m.profit_factor * max(m.win_rate, 1) * max(m.n_trades, 1)
                > best_m.profit_factor * max(best_m.win_rate, 1) * max(best_m.n_trades, 1)
            )
        if better:
            best_p, best_m = p, m
        if passes(m) and m.profit_factor > 1.7 and m.win_rate > 58 and m.n_trades >= 30:
            return p, m
    return best_p, best_m


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline XAUUSD H1 parameter search (no orders)")
    ap.add_argument(
        "--save",
        action="store_true",
        help="write the winning params to strategy_params.json (default: read-only run)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=PARAMS_PATH,
        help=f"destination for --save (default: {PARAMS_PATH.name})",
    )
    ap.add_argument(
        "--to",
        default=None,
        help="fit strictly before this UTC timestamp (default: holdout_start from the lock)",
    )
    ap.add_argument(
        "--unbounded",
        action="store_true",
        help="fit on the whole CSV, ignoring the pre-registered holdout (breaks the protocol)",
    )
    ap.add_argument(
        "--spread-col",
        default="spread",
        help="per-bar spread column in points; '' disables the spread charge",
    )
    ap.add_argument("--commission-per-lot", type=float, default=0.0, help="per lot per side")
    ap.add_argument("--slippage-points", type=float, default=0.0, help="per fill, in points")
    ap.add_argument("--point-size", type=float, default=0.01, help="price per point (XAU: 0.01)")
    args = ap.parse_args(argv)

    global COSTS
    COSTS = {
        "spread_col": args.spread_col or None,
        "point_size": args.point_size,
        "commission_per_lot": args.commission_per_lot,
        "slippage_points": args.slippage_points,
    }

    raw = load_h1()
    cutoff = None
    if args.unbounded:
        print("WARNING: --unbounded — selecting on holdout data; params are NOT protocol-clean.")
    else:
        cutoff = pd.Timestamp(args.to, tz="UTC") if args.to else holdout_start()
        if cutoff is None:
            print(f"WARNING: no holdout lock at {HOLDOUT_LOCK}; fitting on the whole CSV.")
        else:
            full = len(raw)
            raw = develop_only(raw, cutoff)
            print(f"Selection window: time < {cutoff} ({len(raw)}/{full} H1 bars; holdout sealed)")

    d = indicators(raw)
    print(f"Loaded H1 bars={len(d)} {d['time'].iloc[0]} → {d['time'].iloc[-1]}")
    if COSTS.get("spread_col") and COSTS["spread_col"] in d.columns:
        med = float(d[COSTS["spread_col"]].median())
        print(
            f"Costs: spread median {med:.0f} pts (${med * args.point_size:.2f}) "
            f"+ ${args.commission_per_lot:.2f}/lot/side + {args.slippage_points:.0f} pts slippage"
        )
    else:
        print(f"WARNING: no '{args.spread_col}' column — spread charge is 0 (frictionless)")

    print("--- search ---")
    best_p, best_m = search(d)
    print("--- search best ---")
    print_metrics(best_m)
    print(f"params={best_p}")

    if not passes(best_m):
        print("--- refine ---")
        best_p, best_m = refine(d, best_p)
        print("--- refine best ---")
        print_metrics(best_m)
        print(f"params={best_p}")

    # Stage 3: if still short, try scalping high-WR (tight TP, BB only, strong trend)
    if not passes(best_m):
        print("--- stage3 high-WR scalps ---")
        stage3 = []
        for rsi_buy in (40, 45, 50, 55):
            for sl_a, tp_a in ((1.5, 1.2), (2.0, 1.5), (1.2, 1.0), (1.0, 0.8), (2.0, 2.5), (1.5, 2.5)):
                for trend in ("ema50", "ema100", "ema20"):
                    stage3.append(
                        dict(
                            mode="bb_rsi",
                            rsi_buy=float(rsi_buy),
                            rsi_sell=min(70.0, rsi_buy + 15),
                            sl_atr=float(sl_a),
                            tp_atr=float(tp_a),
                            bb_col="bb_lo15",
                            trend_col=trend,
                            use_macd_filter=False,
                            hours=None,
                            long_only=True,
                            risk_pct=0.01,
                            cooldown=0,
                            max_lots=0.3,
                        )
                    )
        for p in stage3:
            m = sim(d, p)
            if passes(m) and (not passes(best_m) or m.profit_factor > best_m.profit_factor):
                best_p, best_m = p, m
            elif not passes(best_m) and m.win_rate > best_m.win_rate and m.profit_factor > 1.2:
                best_p, best_m = p, m
        print("--- stage3 best ---")
        print_metrics(best_m)
        print(f"params={best_p}")

    # Stage 4: dual-side mean reversion without strong trend filter
    if not passes(best_m):
        print("--- stage4 dual MR ---")
        for rsi_buy in (25, 30, 35):
            for sl_a, tp_a in ((1.0, 1.5), (1.2, 2.0), (1.5, 2.5)):
                for req in (True, False):
                    p = dict(
                        mode="bb_rsi",
                        rsi_buy=float(rsi_buy),
                        rsi_sell=55.0,
                        sl_atr=float(sl_a),
                        tp_atr=float(tp_a),
                        bb_col="bb_lo",
                        trend_col="ema200",
                        use_macd_filter=False,
                        hours=None,
                        long_only=False,
                        require_uptrend=req,
                        risk_pct=0.01,
                        cooldown=2,
                    )
                    m = sim(d, p)
                    if passes(m) and (not passes(best_m) or m.net_profit > best_m.net_profit):
                        best_p, best_m = p, m
        print("--- stage4 best ---")
        print_metrics(best_m)
        print(f"params={best_p}")

    print("=== FINAL METRICS ===")
    print_metrics(best_m)

    if args.save:
        args.out.write_text(
            json.dumps(
                {
                    "metrics": {
                        "net_profit": best_m.net_profit,
                        "win_rate": best_m.win_rate,
                        "profit_factor": best_m.profit_factor,
                        "max_drawdown_pct": best_m.max_drawdown_pct,
                        "n_trades": best_m.n_trades,
                    },
                    "params": {
                        k: (list(v) if isinstance(v, tuple) else v) for k, v in best_p.items()
                    },
                    "data": {
                        **data_window(raw),
                        "selection_cutoff": str(cutoff) if cutoff is not None else None,
                        "holdout_sealed": cutoff is not None,
                    },
                    "costs": COSTS,
                    "timeframe": "H1",
                    "start_balance": START_BALANCE,
                },
                indent=2,
            )
        )
        print(f"Wrote {args.out}")
    else:
        print(f"Not saved (read-only run). Pass --save to update {args.out.name}.")
    return 0 if passes(best_m) else 2


if __name__ == "__main__":
    raise SystemExit(main())
