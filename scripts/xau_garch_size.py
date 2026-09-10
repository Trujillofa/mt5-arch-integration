#!/usr/bin/env python3
"""Walk-forward GARCH(1,1) lot overlay on the frozen H1 ``bb_rsi`` host.

Size overlay ``xau_h1_bb_rsi_garch11_invvol_size_v1``. Signal stays frozen
(strategy_params.json). This is not a revival of the null-killed ``bb_rsi``
search family and not a +1/−1 model.

Lock: ``results/xau_garch_size/lock.json`` (written before official metrics).
Holdout ``2026-01-01`` is evaluate-once. Never ``--live``. Never ``backtest.py --save``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from xau_research_costs import (  # noqa: E402
    load_research_costs,
    refuse_mutated_research_costs,
)

import backtest as bt  # noqa: E402

OVERLAY_ID = "xau_h1_bb_rsi_garch11_invvol_size_v1"
LOCK_PATH = _ROOT / "results" / "xau_garch_size" / "lock.json"
OUT_DIR = _ROOT / "results" / "xau_garch_size"
HOLDOUT_START = pd.Timestamp("2026-01-01T00:00:00+00:00")
MIN_LOOKBACK = 500
RECAL_EVERY = 120
RISK_PCT = 0.01
LOT_MIN = 0.01
LOT_MAX = 0.50
LOT_STEP = 0.01
CONSTANT_LOT = 0.10
SIDELINE_Q = 0.95
SL_ATR_DEFAULT = 1.0
PROMOTE = False
LIVE_GO = False


@dataclass(frozen=True)
class HostTrade:
    entry_i: int
    exit_i: int
    side: int
    entry: float
    exit: float
    atr: float
    spread_pts: float
    time: str
    utc_date: str


def load_lock() -> dict:
    if not LOCK_PATH.is_file():
        raise SystemExit(f"missing overlay lock: {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("overlay_id") != OVERLAY_ID:
        raise SystemExit("lock overlay_id mismatch")
    if lock.get("promote") is True or lock.get("live_go") is True:
        raise SystemExit("lock promote/live_go must stay false")
    if not lock.get("frozen_before_metrics"):
        raise SystemExit("lock must be frozen_before_metrics")
    return lock


def load_host_params() -> dict:
    saved = json.loads((_ROOT / "strategy_params.json").read_text())
    params = bt.normalize_params(saved["params"])
    window = saved["data"]
    return {"params": params, "window": window, "saved": saved}


def load_develop_h1() -> tuple[pd.DataFrame, dict]:
    host = load_host_params()
    raw = bt.load_h1()
    d = bt.slice_to_window(raw, host["window"])
    return bt.indicators(d), host


def load_full_h1() -> pd.DataFrame:
    return bt.indicators(bt.load_h1())


def collect_host_trades(
    d: pd.DataFrame,
    params: dict,
    costs: dict,
    *,
    max_lots: float = LOT_MAX,
) -> list[HostTrade]:
    """Replay host signal + ATR exits. Lots use host ATR-lot skip rules."""
    n = len(d)
    close = d["close"].to_numpy(float)
    high = d["high"].to_numpy(float)
    low = d["low"].to_numpy(float)
    rsi = d["rsi"].to_numpy(float)
    atr = d["atr"].to_numpy(float)
    bb_col = params["bb_col"]
    bb_lo = d[bb_col].to_numpy(float)
    bb_mid = d["bb_mid"].to_numpy(float)
    bb_up = d["bb_up"].to_numpy(float)
    trend = d[params["trend_col"]].to_numpy(float)
    macd_h = d["macd_hist"].to_numpy(float)
    hour = d["hour"].to_numpy(int)
    times = pd.to_datetime(d["time"], utc=True)
    spread_col = costs.get("spread_col")
    if spread_col and spread_col in d.columns:
        spread_pts = np.nan_to_num(d[spread_col].to_numpy(float), nan=0.0)
    else:
        spread_pts = np.zeros(n)

    sl_atr = float(params["sl_atr"])
    tp_atr = float(params["tp_atr"])
    rsi_buy = float(params["rsi_buy"])
    rsi_sell = float(params["rsi_sell"])
    risk_pct = float(params.get("risk_pct", RISK_PCT))
    cooldown = int(params.get("cooldown", 2))
    hours = params.get("hours")
    long_only = bool(params.get("long_only", True))
    use_macd = bool(params.get("use_macd_filter", False))
    mode = params.get("mode", "bb_rsi")
    contract = bt.CONTRACT_SIZE
    point = float(costs.get("point_size", 0.01))
    slip = float(costs.get("slippage_points", 0.0))
    comm = float(costs.get("commission_per_lot", 0.0))

    bal = bt.START_BALANCE
    pos = 0
    entry = sl = tp = lots = 0.0
    trade_cost = 0.0
    cool = 0
    warmup = 220
    entry_i = 0
    entry_atr = 0.0
    entry_spr = 0.0
    entry_side = 0
    trades: list[HostTrade] = []

    def _close_trade(i: int, exit_px: float) -> None:
        nonlocal bal, pos, lots, trade_cost
        pnl = (exit_px - entry) * contract * lots * pos - trade_cost
        bal += pnl
        trades.append(
            HostTrade(
                entry_i=entry_i,
                exit_i=i,
                side=entry_side,
                entry=float(entry),
                exit=float(exit_px),
                atr=float(entry_atr),
                spread_pts=float(entry_spr),
                time=str(times.iloc[entry_i]),
                utc_date=str(times.iloc[entry_i].date()),
            )
        )
        pos = 0
        lots = 0.0
        trade_cost = 0.0

    for i in range(n):
        px = close[i]
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
                _close_trade(i, float(exit_px))
                cool = cooldown

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
        if long_only and not uptrend:
            continue
        if use_macd and macd_h[i] < 0 and long_only:
            continue

        long_sig = False
        short_sig = False
        if mode == "bb_rsi":
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
        else:
            continue
        if not long_sig and not short_sig:
            continue

        stop_dist = atr[i] * sl_atr
        if stop_dist <= 1e-9:
            continue
        risk_cash = bal * risk_pct
        raw = risk_cash / (stop_dist * contract)
        host_lots = float(np.floor(raw * 100 + 1e-12) / 100.0)
        host_lots = min(host_lots, max_lots)
        min_lot_risk = stop_dist * contract * LOT_MIN
        if host_lots < LOT_MIN or min_lot_risk > risk_cash + 1e-9:
            continue

        trade_cost = (spread_pts[i] + 2.0 * slip) * point * contract * host_lots + 2.0 * comm * host_lots
        entry_i = i
        entry_atr = atr[i]
        entry_spr = spread_pts[i]
        if long_sig:
            pos = 1
            entry_side = 1
            entry = px
            sl = entry - stop_dist
            tp = entry + atr[i] * tp_atr
            lots = host_lots
        else:
            pos = -1
            entry_side = -1
            entry = px
            sl = entry + stop_dist
            tp = entry - atr[i] * tp_atr
            lots = host_lots

    if pos != 0:
        _close_trade(n - 1, float(close[-1]))
    return trades


# ---------------------------------------------------------------------------
# GARCH(1,1) — variance targeting, walk-forward
# ---------------------------------------------------------------------------


def garch11_filter(
    returns: np.ndarray,
    omega: float,
    alpha: float,
    beta: float,
    var0: float,
) -> np.ndarray:
    n = int(returns.shape[0])
    var = np.empty(n, dtype=float)
    v = float(max(var0, 1e-16))
    var[0] = v
    for t in range(1, n):
        v = omega + alpha * returns[t - 1] ** 2 + beta * v
        if v < 1e-16:
            v = 1e-16
        var[t] = v
    return var


def _garch_nll(params: np.ndarray, returns: np.ndarray, var_target: float) -> float:
    alpha, beta = float(params[0]), float(params[1])
    if alpha <= 0.0 or beta <= 0.0 or alpha + beta >= 0.999:
        return 1e12
    omega = (1.0 - alpha - beta) * var_target
    var = garch11_filter(returns, omega, alpha, beta, var_target)
    return float(0.5 * np.sum(np.log(var) + returns**2 / var))


def fit_garch11(returns: np.ndarray) -> tuple[float, float, float]:
    """Variance-targeted GARCH(1,1). Returns (omega, alpha, beta)."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 50:
        vt = float(np.var(r)) if r.size else 1e-6
        return (0.05 * vt, 0.05, 0.90)
    vt = float(np.var(r))
    best_nll = 1e18
    best = (0.05, 0.90)
    for a in (0.03, 0.05, 0.08, 0.12):
        for b in (0.80, 0.88, 0.92, 0.95):
            if a + b >= 0.999:
                continue
            nll = _garch_nll(np.array([a, b]), r, vt)
            if nll < best_nll:
                best_nll = nll
                best = (a, b)
    alpha, beta = best
    # Coordinate descent polish (no scipy — uv pytest venv has none).
    for _ in range(8):
        improved = False
        for da, db in ((0.01, 0.0), (-0.01, 0.0), (0.0, 0.01), (0.0, -0.01), (0.005, -0.005)):
            a2, b2 = alpha + da, beta + db
            if a2 <= 1e-4 or b2 <= 0.50 or a2 + b2 >= 0.999 or a2 > 0.35 or b2 > 0.989:
                continue
            nll = _garch_nll(np.array([a2, b2]), r, vt)
            if nll < best_nll:
                best_nll = nll
                alpha, beta = a2, b2
                improved = True
        if not improved:
            break
    omega = (1.0 - alpha - beta) * vt
    return (float(omega), float(alpha), float(beta))


def log_returns(close: np.ndarray) -> np.ndarray:
    c = np.asarray(close, dtype=float)
    out = np.full(c.shape[0], np.nan)
    out[1:] = np.log(c[1:] / c[:-1])
    return out


def walkforward_sigma(
    close: np.ndarray,
    *,
    min_lookback: int = MIN_LOOKBACK,
    recal_every: int = RECAL_EVERY,
) -> np.ndarray:
    """1-step σ̂ at bar i from returns strictly before i. Causal.

    Refit every ``recal_every`` bars; between fits the variance is updated
    recursively so we do not refilter the whole history each bar.
    """
    r = log_returns(close)
    n = int(close.shape[0])
    sigma = np.full(n, np.nan)
    omega = alpha = beta = None
    last_var = None
    last_fit = -10**9
    for i in range(n):
        if i < min_lookback + 1:
            continue
        hist = r[1:i]
        if hist.size < min_lookback or not np.isfinite(hist[-1]):
            continue
        if omega is None or i - last_fit >= recal_every:
            omega, alpha, beta = fit_garch11(hist)
            vt = float(np.var(hist[np.isfinite(hist)]))
            var = garch11_filter(hist, omega, alpha, beta, vt)
            last_var = float(var[-1])
            last_fit = i
        last_r = float(hist[-1])
        var_fwd = omega + alpha * last_r**2 + beta * last_var
        if var_fwd < 1e-16:
            var_fwd = 1e-16
        sigma[i] = float(np.sqrt(var_fwd))
        last_var = float(var_fwd)
    return sigma


def expanding_sideline_mask(sigma: np.ndarray, q: float = SIDELINE_Q) -> np.ndarray:
    """True = sideline. Threshold from past forecasts only."""
    n = int(sigma.shape[0])
    mask = np.zeros(n, dtype=bool)
    past: list[float] = []
    for i in range(n):
        s = sigma[i]
        if past and np.isfinite(s):
            thr = float(np.quantile(np.asarray(past, dtype=float), q))
            if s > thr:
                mask[i] = True
        if np.isfinite(s):
            past.append(float(s))
    return mask


def _floor_lot(raw: float) -> float | None:
    if not np.isfinite(raw) or raw < LOT_MIN:
        return None
    lots = float(np.floor(raw / LOT_STEP + 1e-12) * LOT_STEP)
    lots = min(lots, LOT_MAX)
    if lots < LOT_MIN - 1e-15:
        return None
    return lots


def atr_lots(balance: float, atr: float, sl_atr: float) -> float | None:
    if atr <= 0 or sl_atr <= 0:
        return None
    return _floor_lot(balance * RISK_PCT / (atr * sl_atr * bt.CONTRACT_SIZE))


def garch_lots(balance: float, sigma_ret: float, close: float, sl_atr: float) -> float | None:
    if not np.isfinite(sigma_ret) or sigma_ret <= 0 or close <= 0:
        return None
    sigma_px = sigma_ret * close
    return _floor_lot(balance * RISK_PCT / (sigma_px * sl_atr * bt.CONTRACT_SIZE))


def replay_sized(
    trades: list[HostTrade],
    d: pd.DataFrame,
    costs: dict,
    *,
    sl_atr: float,
    lot_fn: Callable[..., float | None],
    sigma: np.ndarray | None = None,
    sideline: np.ndarray | None = None,
) -> dict[str, Any]:
    close = d["close"].to_numpy(float)
    point = float(costs.get("point_size", 0.01))
    slip = float(costs.get("slippage_points", 0.0))
    comm = float(costs.get("commission_per_lot", 0.0))
    contract = bt.CONTRACT_SIZE
    bal = bt.START_BALANCE
    equity = [bal]
    pnls: list[float] = []
    n_side = 0
    n_skip = 0
    for tr in trades:
        if sideline is not None and bool(sideline[tr.entry_i]):
            n_side += 1
            continue
        if lot_fn.__name__ == "garch_lots":
            sig = float(sigma[tr.entry_i]) if sigma is not None else float("nan")
            if not np.isfinite(sig):
                lots = atr_lots(bal, tr.atr, sl_atr)
            else:
                lots = garch_lots(bal, sig, close[tr.entry_i], sl_atr)
        elif lot_fn.__name__ == "constant_lots":
            lots = CONSTANT_LOT
        else:
            lots = atr_lots(bal, tr.atr, sl_atr)
        if lots is None:
            n_skip += 1
            continue
        cost = (tr.spread_pts + 2.0 * slip) * point * contract * lots + 2.0 * comm * lots
        pnl = (tr.exit - tr.entry) * tr.side * contract * lots - cost
        bal += pnl
        pnls.append(float(pnl))
        equity.append(bal)
    eq = np.asarray(equity, dtype=float)
    m = bt.metrics_from_pnls(pnls, eq)
    return {
        "n_host": len(trades),
        "n_taken": int(m.n_trades),
        "n_sidelined": n_side,
        "n_skip_lot": n_skip,
        "net_profit": float(m.net_profit),
        "win_rate": float(m.win_rate) / 100.0,
        "win_rate_pct": float(m.win_rate),
        "profit_factor": float(m.profit_factor),
        "max_drawdown_pct": float(m.max_drawdown_pct),
        "wins": int(m.wins),
        "losses": int(m.losses),
        "end_balance": float(bal),
    }


def constant_lots(*_a, **_k) -> float:
    return CONSTANT_LOT


def pick_winner(rows: dict[str, dict]) -> str:
    """Develop-only. Max PF, tie-break net. Does not see holdout."""
    names = list(rows)
    names.sort(
        key=lambda k: (-float(rows[k]["profit_factor"]), -float(rows[k]["net_profit"]))
    )
    return names[0]


def garch_beats_atr(garch: dict, atr: dict) -> bool:
    pf_g, pf_a = float(garch["profit_factor"]), float(atr["profit_factor"])
    if pf_g > pf_a:
        return True
    return pf_g == pf_a and float(garch["net_profit"]) > float(atr["net_profit"])


def _window_trades(trades: list[HostTrade], *, holdout: bool) -> list[HostTrade]:
    out = []
    for tr in trades:
        d = pd.Timestamp(tr.time)
        if d.tzinfo is None:
            d = d.tz_localize("UTC")
        if holdout and d >= HOLDOUT_START or not holdout and d < HOLDOUT_START:
            out.append(tr)
    return out


def run_book(
    d: pd.DataFrame,
    trades: list[HostTrade],
    costs: dict,
    sl_atr: float,
) -> tuple[dict[str, dict], np.ndarray]:
    close = d["close"].to_numpy(float)
    sigma = walkforward_sigma(close)
    side = expanding_sideline_mask(sigma, SIDELINE_Q)
    books = {
        "constant_lot_0.10": replay_sized(
            trades, d, costs, sl_atr=sl_atr, lot_fn=constant_lots
        ),
        "atr_lot_host": replay_sized(
            trades, d, costs, sl_atr=sl_atr, lot_fn=atr_lots
        ),
        "garch11_invvol": replay_sized(
            trades, d, costs, sl_atr=sl_atr, lot_fn=garch_lots, sigma=sigma, sideline=side
        ),
    }
    return books, sigma


def slim(books: dict[str, dict]) -> dict[str, dict]:
    keep = (
        "n_host",
        "n_taken",
        "n_sidelined",
        "net_profit",
        "win_rate_pct",
        "profit_factor",
        "max_drawdown_pct",
    )
    return {k: {kk: v[kk] for kk in keep} for k, v in books.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--eval-holdout", action="store_true")
    ap.add_argument("--assumed-slip", type=float, default=None, help="labeled sensitivity, not official")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    load_lock()
    costs = load_research_costs()
    refuse_mutated_research_costs(costs)
    if args.assumed_slip is not None:
        costs = dict(costs)
        costs["slippage_points"] = float(args.assumed_slip)

    host = load_host_params()
    params = host["params"]
    sl_atr = float(params["sl_atr"])
    d_dev = bt.indicators(bt.slice_to_window(bt.load_h1(), host["window"]))
    trades_dev = collect_host_trades(d_dev, params, costs)
    books_dev, _ = run_book(d_dev, trades_dev, costs, sl_atr)
    winner = pick_winner(books_dev)
    beats = garch_beats_atr(books_dev["garch11_invvol"], books_dev["atr_lot_host"])
    verdict = "continue" if beats else "kill"

    print("=== DEVELOP (slice_to_window, selection) ===")
    print(f"overlay {OVERLAY_ID}  n_host={len(trades_dev)}  thin_n=yes")
    print(f"{'book':22} {'n':>4} {'WR%':>7} {'PF':>8} {'NP':>10} {'DD%':>7} side")
    for name, m in books_dev.items():
        print(
            f"{name:22} {m['n_taken']:4d} {m['win_rate_pct']:7.1f} "
            f"{m['profit_factor']:8.3f} {m['net_profit']:10.1f} "
            f"{m['max_drawdown_pct']:7.2f} {m['n_sidelined']}"
        )
    print(f"winner_by_lock_score={winner}  garch_beats_atr={beats}  verdict={verdict}")
    print(
        "costs: slip=0 UNMEASURED (official book)"
        + (f"; this run assumed_slip={args.assumed_slip} (not official)" if args.assumed_slip is not None else "")
    )

    payload = {
        "overlay_id": OVERLAY_ID,
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "thin_n": True,
        "n_host_develop": len(trades_dev),
        "winner": winner,
        "garch_beats_atr": beats,
        "verdict": verdict,
        "score_window": "develop",
        "costs": costs,
        "slip_label": "UNMEASURED" if args.assumed_slip is None else f"assumed_{args.assumed_slip}",
        "develop": slim(books_dev),
        "lock": str(LOCK_PATH.relative_to(_ROOT)),
    }

    holdout_printed = False
    if args.eval_holdout:
        d_full = load_full_h1()
        trades_all = collect_host_trades(d_full, params, costs)
        ho = _window_trades(trades_all, holdout=True)
        # Walk-forward sigma on full tape (develop history is knowable in holdout).
        books_ho, _ = run_book(d_full, ho, costs, sl_atr)
        payload["holdout"] = slim(books_ho)
        payload["n_host_holdout"] = len(ho)
        print("=== HOLDOUT (evaluate once, not used to pick) ===")
        print(f"{'book':22} {'n':>4} {'WR%':>7} {'PF':>8} {'NP':>10} {'DD%':>7}")
        for name, m in books_ho.items():
            print(
                f"{name:22} {m['n_taken']:4d} {m['win_rate_pct']:7.1f} "
                f"{m['profit_factor']:8.3f} {m['net_profit']:10.1f} "
                f"{m['max_drawdown_pct']:7.2f}"
            )
        holdout_printed = True
    else:
        print("holdout: not printed (pass --eval-holdout after lock)")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.assumed_slip is None:
        (args.out_dir / "develop.json").write_text(json.dumps(payload, indent=2) + "\n")
        if holdout_printed:
            (args.out_dir / "holdout.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.out_dir / 'develop.json'}")
    else:
        (args.out_dir / f"sensitivity_slip{args.assumed_slip:g}.json").write_text(
            json.dumps(payload, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
