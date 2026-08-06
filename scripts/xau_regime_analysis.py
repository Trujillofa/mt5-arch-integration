#!/usr/bin/env python3
"""Train vs OOS regime analysis for XAU H1 (fixed strategy_params, no live orders)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest import indicators, load_h1, simulate  # noqa: E402

OUT_PATH = ROOT / "results" / "xau_regime_analysis.json"
HOLDOUT_PATH = ROOT / "results" / "xau_oos_holdout.json"
PARAMS_PATH = ROOT / "strategy_params.json"


def _normalize_params(raw: dict) -> dict:
    p = dict(raw)
    if isinstance(p.get("hours"), list):
        p["hours"] = tuple(p["hours"]) if p["hours"] else None
    return p


def long_signal_mask(d: pd.DataFrame, params: dict) -> pd.Series:
    """Bar-level long entry conditions mirroring simulate() bb_rsi / rsi_cross / macd_pullback."""
    mode = params.get("mode", "bb_rsi")
    rsi_buy = float(params.get("rsi_buy", 35.0))
    bb_col = params.get("bb_col", "bb_lo")
    trend_col = params.get("trend_col", "ema100")
    require_uptrend = params.get("require_uptrend", True)
    use_macd = bool(params.get("use_macd_filter", False))
    hours = params.get("hours")
    warmup = 220

    close = d["close"]
    low = d["low"]
    high = d["high"]
    rsi = d["rsi"]
    atr = d["atr"]
    bb_lo = d[bb_col]
    bb_mid = d["bb_mid"]
    trend = d[trend_col]
    macd_h = d["macd_hist"]
    hour = d["hour"]

    uptrend = close > trend
    ok = (
        (np.arange(len(d)) >= warmup)
        & atr.notna()
        & rsi.notna()
        & (atr > 0)
    )
    if hours is not None:
        ok &= hour.isin(list(hours))
    if require_uptrend:
        ok &= uptrend
    if use_macd:
        ok &= macd_h >= 0

    if mode == "bb_rsi":
        long_sig = (
            uptrend
            & (low <= bb_lo)
            & (close > bb_lo)
            & (close < bb_mid)
            & (rsi <= rsi_buy + 10)
        )
    elif mode == "rsi_cross":
        rsi_prev = rsi.shift(1)
        long_sig = uptrend & (rsi_prev < rsi_buy) & (rsi >= rsi_buy)
    elif mode == "macd_pullback":
        macd_prev = macd_h.shift(1)
        long_sig = (
            uptrend
            & (macd_prev < 0)
            & (macd_h >= 0)
            & (rsi < rsi_buy + 15)
            & (close > d["ema20"])
        )
    else:
        long_sig = pd.Series(False, index=d.index)

    return ok & long_sig.fillna(False)


def segment_stats(d: pd.DataFrame, label: str) -> dict:
    close = d["close"].astype(float)
    rets = close.pct_change().dropna()
    atr = d["atr"].dropna()
    rsi = d["rsi"].dropna()
    bb_width = ((d["bb_up"] - d["bb_lo"]) / d["bb_mid"]).replace([np.inf, -np.inf], np.nan).dropna()
    above_ema200 = (close > d["ema200"]).mean()
    return {
        "label": label,
        "n_bars": int(len(d)),
        "time_start": str(d["time"].iloc[0]),
        "time_end": str(d["time"].iloc[-1]),
        "close_return_mean": float(rets.mean()) if len(rets) else None,
        "close_return_std": float(rets.std()) if len(rets) else None,
        "atr_mean": float(atr.mean()) if len(atr) else None,
        "atr_std": float(atr.std()) if len(atr) else None,
        "rsi_mean": float(rsi.mean()) if len(rsi) else None,
        "rsi_std": float(rsi.std()) if len(rsi) else None,
        "bb_width_mean": float(bb_width.mean()) if len(bb_width) else None,
        "bb_width_std": float(bb_width.std()) if len(bb_width) else None,
        "frac_close_gt_ema200": float(above_ema200),
    }


def metrics_dict(m) -> dict:
    return {
        "net_profit": m.net_profit,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "max_drawdown_pct": m.max_drawdown_pct,
        "n_trades": m.n_trades,
        "wins": m.wins,
        "losses": m.losses,
    }


def monthly_signal_counts(d: pd.DataFrame, sig: pd.Series) -> dict[str, int]:
    t = pd.to_datetime(d["time"], utc=True)
    months = t.dt.strftime("%Y-%m")
    counts: dict[str, int] = {}
    for m, s in zip(months, sig.to_numpy(), strict=False):
        if s:
            counts[m] = counts.get(m, 0) + 1
    # include zero months that appear in data
    for m in sorted(months.unique()):
        counts.setdefault(m, 0)
    return dict(sorted(counts.items()))


def resolve_split(d: pd.DataFrame) -> tuple[pd.Timestamp, str]:
    """Use holdout file split if present; else 70% by time."""
    if HOLDOUT_PATH.is_file():
        hold = json.loads(HOLDOUT_PATH.read_text())
        split_str = hold.get("split")
        if split_str:
            ts = pd.Timestamp(split_str)
            return ts, f"from {HOLDOUT_PATH.name}"
    t0 = pd.to_datetime(d["time"].iloc[0], utc=True)
    t1 = pd.to_datetime(d["time"].iloc[-1], utc=True)
    split = t0 + 0.7 * (t1 - t0)
    return split, "computed 70% time"


def main() -> int:
    raw = load_h1()
    d = indicators(raw)
    params = _normalize_params(json.loads(PARAMS_PATH.read_text())["params"])

    split_ts, split_src = resolve_split(d)
    times = pd.to_datetime(d["time"], utc=True)
    # align split tz
    if split_ts.tzinfo is None:
        split_ts = split_ts.tz_localize("UTC")
    else:
        split_ts = split_ts.tz_convert("UTC")

    train = d.loc[times < split_ts].reset_index(drop=True)
    oos = d.loc[times >= split_ts].reset_index(drop=True)

    train_stats = segment_stats(train, "train")
    oos_stats = segment_stats(oos, "oos")

    print("=== Regime features ===")
    for s in (train_stats, oos_stats):
        print(
            f"{s['label']}: bars={s['n_bars']} ret_mean={s['close_return_mean']:.6e} "
            f"ret_std={s['close_return_std']:.6e} atr_mean={s['atr_mean']:.4f} "
            f"rsi_mean={s['rsi_mean']:.2f} bb_w={s['bb_width_mean']:.6f} "
            f"frac>ema200={s['frac_close_gt_ema200']:.3f}"
        )

    train_m = simulate(train, **params)
    oos_m = simulate(oos, **params)
    print("=== Simulate (fixed params) ===")
    print(f"train: {metrics_dict(train_m)}")
    print(f"oos:   {metrics_dict(oos_m)}")

    train_sig = long_signal_mask(train, params)
    oos_sig = long_signal_mask(oos, params)
    train_monthly = monthly_signal_counts(train, train_sig)
    oos_monthly = monthly_signal_counts(oos, oos_sig)

    print("=== Monthly long-signal bars (proxy) ===")
    print(f"train total signals: {int(train_sig.sum())}")
    print(f"oos total signals:   {int(oos_sig.sum())}")
    print(f"train monthly: {train_monthly}")
    print(f"oos monthly:   {oos_monthly}")

    # simple regime-shift flags
    def ratio(a, b):
        if a is None or b is None or b == 0:
            return None
        return float(a / b)

    comparison = {
        "ret_std_oos_over_train": ratio(oos_stats["close_return_std"], train_stats["close_return_std"]),
        "atr_mean_oos_over_train": ratio(oos_stats["atr_mean"], train_stats["atr_mean"]),
        "bb_width_oos_over_train": ratio(oos_stats["bb_width_mean"], train_stats["bb_width_mean"]),
        "frac_above_ema200_delta": float(
            oos_stats["frac_close_gt_ema200"] - train_stats["frac_close_gt_ema200"]
        ),
        "rsi_mean_delta": float(oos_stats["rsi_mean"] - train_stats["rsi_mean"])
        if oos_stats["rsi_mean"] is not None and train_stats["rsi_mean"] is not None
        else None,
        "signal_rate_train_per_bar": float(train_sig.mean()) if len(train) else 0.0,
        "signal_rate_oos_per_bar": float(oos_sig.mean()) if len(oos) else 0.0,
    }

    out = {
        "split": str(split_ts),
        "split_source": split_src,
        "params": {k: (list(v) if isinstance(v, tuple) else v) for k, v in params.items()},
        "train": {
            **train_stats,
            "metrics": metrics_dict(train_m),
            "long_signal_bars": int(train_sig.sum()),
            "monthly_long_signals": train_monthly,
        },
        "oos": {
            **oos_stats,
            "metrics": metrics_dict(oos_m),
            "long_signal_bars": int(oos_sig.sum()),
            "monthly_long_signals": oos_monthly,
        },
        "comparison": comparison,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
