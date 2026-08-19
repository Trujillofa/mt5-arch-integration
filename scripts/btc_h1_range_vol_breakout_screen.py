#!/usr/bin/env python3
"""BTCUSD H1 range + vol-expansion breakout screen (`btc_h1_range_vol_breakout_v1`).

Lock: results/btc_h1_range_vol_breakout_v1_lock.json
  select signal_utc_date < 2026-01-01
  holdout >= 2026-01-01  (never used for selection)

No H4 EMA stack. Book is 0.01 lot / 250 pt slip.
1%/20% is not a pass gate. promote / live_go stay no.

SAFETY: offline only. Reads native .hc; does not kill terminal64.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time as pytime
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from btc_range_vol_breakout_core import (  # noqa: E402
    ATR_FAST,
    FROZEN_LOTS,
    FROZEN_SLIPPAGE_POINTS,
    HOLDOUT_START,
    MAX_DD_PCT_MAX,
    N_TRADES_MIN,
    PF_MIN,
    SEARCH_ID,
    START_BALANCE,
    TP_RR,
    breakout_signals,
    frozen_cost_spec,
    refuse_mutated_btc_book,
    require_frozen_btc_book,
    split_btc,
)
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    Trade,
    hc_to_export_csv,
    load_m5_csv,
    metrics_from_trades,
    read_mt5_hc,
    write_slim_json,
)
from us_index_session_core import to_utc, wilder_atr  # noqa: E402
from us_index_session_htf import simulate_htf_exits  # noqa: E402

LOCK_PATH = _ROOT / "results" / "btc_h1_range_vol_breakout_v1_lock.json"
DATA_DIR = _ROOT / "results" / "btc_data"
FP_BTC_CACHE = (
    Path.home()
    / ".mt5-fpmarkets"
    / "drive_c"
    / "Program Files"
    / "FP Markets MT5 Terminal"
    / "Bases"
    / "FPMarketsSC-Live"
    / "history"
    / "BTCUSD"
    / "cache"
)
RANGE_N = (20, 40)
SQUEEZE_MAX = (0.75, 0.90)
EXPAND_MIN = (1.25, 1.75)
SL_ATR = (1.5, 2.0)


def load_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text())
    refuse_mutated_btc_book(lock)
    return lock


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for rn, sq, ex, sl in itertools.product(RANGE_N, SQUEEZE_MAX, EXPAND_MIN, SL_ATR):
        rows.append(
            {
                "family": "h1_range_vol_breakout",
                "range_n": rn,
                "squeeze_max": sq,
                "expand_min": ex,
                "sl_atr": sl,
                "tp_rr": TP_RR,
                "flatten_weekend": True,
                "allow_shorts": True,
            }
        )
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_btc_h1_csv(cache_dir: Path, out_dir: Path) -> dict[str, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    src = cache_dir / "H1.hc"
    csv = out_dir / "history_BTCUSD_H1.csv"
    hc_to_export_csv(src, csv, "BTCUSD", tf="H1")
    df = read_mt5_hc(src)
    return {
        "H1": {
            "path": str(csv.relative_to(_ROOT)),
            "sha256": _sha256(csv),
            "bars": int(len(df)),
        }
    }


def daily_monthly(trades: list[Trade], balance: float = START_BALANCE) -> dict:
    if balance <= 0:
        balance = START_BALANCE
    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        by_day[str(t.signal_time)[:10]] += t.pnl
    day_pcts = [p / balance for p in by_day.values()] if by_day else []
    by_month: dict[str, float] = defaultdict(float)
    for d, p in by_day.items():
        by_month[d[:7]] += p
    month_pcts = [p / balance for p in by_month.values()] if by_month else []
    return {
        "trade_days": len(by_day),
        "median_daily_pct": float(np.median(day_pcts)) if day_pcts else 0.0,
        "mean_daily_pct": float(np.mean(day_pcts)) if day_pcts else 0.0,
        "trade_months": len(by_month),
        "median_monthly_pct": float(np.median(month_pcts)) if month_pcts else 0.0,
        "mean_monthly_pct": float(np.mean(month_pcts)) if month_pcts else 0.0,
    }


def pack_metrics(trades: list[Trade]) -> dict:
    m = metrics_from_trades(trades)
    m.update(daily_monthly(trades))
    dd = abs(float(m["max_dd"]))
    m["max_dd_pct"] = dd / START_BALANCE
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    m["soft_pass"] = bool(
        int(m["trades"]) >= N_TRADES_MIN
        and float(m["net_pnl"]) > 0.0
        and pf_v >= PF_MIN
        and float(m["max_dd_pct"]) <= MAX_DD_PCT_MAX
    )
    m["goal_both"] = False
    return m


def score_row(m: dict) -> float:
    """Develop-only rank. Holdout fields must never enter this function."""
    if int(m["trades"]) < N_TRADES_MIN or float(m["net_pnl"]) <= 0:
        return -1e9
    pf = m["profit_factor"]
    pf_v = 3.0 if pf is None else float(pf)
    return pf_v * 1000.0 + float(m["expectancy"])


def _run(
    cfg: dict,
    times: list,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: np.ndarray,
    spread: np.ndarray,
    dow: np.ndarray,
    costs: CostSpec,
    sigs: np.ndarray,
) -> dict:
    trades = simulate_htf_exits(
        times,
        open_,
        high,
        low,
        spread,
        sigs,
        costs,
        atr=atr,
        sl_mult=float(cfg["sl_atr"]),
        tp_mult=float(cfg["sl_atr"]) * float(cfg["tp_rr"]),
        flatten_friday=True,
        dow=dow,
    )
    pre, post = split_btc(trades)
    return {
        "params": dict(cfg),
        "develop": pack_metrics(pre),
        "holdout": pack_metrics(post),
        "develop_score": score_row(pack_metrics(pre)),
        "holdout_trades": int(len(post)),
    }


def run_search(h1_csv: Path, costs: CostSpec, offset: int = 10800) -> dict:
    require_frozen_btc_book(costs)
    h1 = load_m5_csv(h1_csv, offset)
    times = [to_utc(ts.to_pydatetime()) for ts in h1["time_utc"]]
    high = h1["high"].to_numpy(float)
    low = h1["low"].to_numpy(float)
    close = h1["close"].to_numpy(float)
    open_ = h1["open"].to_numpy(float)
    spread = h1["spread"].to_numpy(float)
    atr = wilder_atr(high, low, close, ATR_FAST)
    dow = np.array([to_utc(t).weekday() for t in times], dtype=np.int8)

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    cache: dict[tuple, np.ndarray] = {}
    for i, cfg in enumerate(grid):
        key = (int(cfg["range_n"]), float(cfg["squeeze_max"]), float(cfg["expand_min"]))
        if key not in cache:
            cache[key] = breakout_signals(
                close,
                high,
                low,
                range_n=key[0],
                squeeze_max=key[1],
                expand_min=key[2],
                allow_shorts=True,
            )
        row = _run(cfg, times, open_, high, low, atr, spread, dow, costs, cache[key])
        row["index"] = i
        rows.append(row)
    elapsed = pytime.time() - t0
    eligible = [r for r in rows if r["develop_score"] > -1e8]
    ranked = sorted(
        eligible,
        key=lambda r: (
            r["develop"]["profit_factor"] or 3.0,
            r["develop"]["expectancy"],
        ),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    n_soft = sum(1 for r in eligible if r["develop"]["soft_pass"])
    n_ho = sum(1 for r in ranked[:20] if r["holdout"]["soft_pass"])
    n_ho_any = sum(1 for r in rows if r["holdout"]["soft_pass"])
    n_ho_trades = sum(1 for r in rows if int(r["holdout"]["trades"]) > 0)
    raw = sorted(
        rows,
        key=lambda r: (
            r["develop"]["profit_factor"] or 0.0,
            r["develop"]["expectancy"],
            r["develop"]["trades"],
        ),
        reverse=True,
    )
    grid_rows = [
        {
            "params": r["params"],
            "develop": {
                k: r["develop"][k]
                for k in (
                    "trades",
                    "win_rate",
                    "profit_factor",
                    "net_pnl",
                    "max_dd_pct",
                    "median_daily_pct",
                    "longs",
                    "shorts",
                    "soft_pass",
                )
            },
            "holdout": {
                k: r["holdout"][k]
                for k in (
                    "trades",
                    "win_rate",
                    "profit_factor",
                    "net_pnl",
                    "max_dd_pct",
                    "median_daily_pct",
                    "longs",
                    "shorts",
                    "soft_pass",
                )
            },
        }
        for r in rows
    ]
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "python_only": True,
        "selection_end": str(HOLDOUT_START),
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "lots": FROZEN_LOTS,
        "slippage_points": FROZEN_SLIPPAGE_POINTS,
        "n_configs": len(rows),
        "n_eligible": len(eligible),
        "n_develop_soft_pass": n_soft,
        "n_top20_holdout_soft_pass": n_ho,
        "n_holdout_soft_pass_any": n_ho_any,
        "n_holdout_with_trades": n_ho_trades,
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars_h1": int(len(h1)),
        "from": str(h1["time_utc"].iloc[0]) if len(h1) else "",
        "to": str(h1["time_utc"].iloc[-1]) if len(h1) else "",
        "data_source": "FP native H1.hc via read_mt5_hc (H4 not used)",
        "best_develop": best,
        "best_raw_develop": raw[0] if raw else None,
        "grid": grid_rows,
        "note": (
            "Path 1b.2. H1 range close-through + ATR squeeze/expand. "
            "No EMA/H4. 0.01 lot / 250 pt slip. 1%/20% is not a gate. promote=no."
        ),
    }


def write_report_md(report: dict, path: Path) -> None:
    best = report.get("best_develop") or report.get("best_raw_develop")
    elig = int(report["n_eligible"])
    soft = int(report["n_develop_soft_pass"])
    ho = int(report["n_top20_holdout_soft_pass"])
    ho_n = int(report.get("n_holdout_with_trades") or 0)

    def _row(m: dict) -> str:
        pf = m.get("profit_factor")
        pf_s = "inf" if pf is None else f"{pf:.2f}"
        return (
            f"{m['trades']} | {100.0 * m['win_rate']:.0f}% | {pf_s} | "
            f"{m['net_pnl']:+.2f} | {100.0 * m['max_dd_pct']:.2f}% | "
            f"{100.0 * m['median_daily_pct']:+.4f}%"
        )

    lines = [
        "# BTC H1 range / vol-breakout screen (`btc_h1_range_vol_breakout_v1`)",
        "",
        "| Field | Value |",
        "|-------|--------|",
        "| **Date** | 2026-08-19 |",
        "| **Search** | `btc_h1_range_vol_breakout_v1` — H1 close-through + squeeze→expand |",
        "| **Lock** | `results/btc_h1_range_vol_breakout_v1_lock.json` |",
        "| **Grill** | `results/btc_h1_range_vol_breakout_v1_grill.md` (frozen before grid) |",
        "| **Select** | `signal_utc_date < 2026-01-01` |",
        "| **Holdout** | **2026-01-01** onward. Never used for selection. |",
        "| **Book** | $10,000 / **0.01 lot** / **250 pt** slip/side / point 0.01 / contract 1 |",
        f"| **Grid** | {report['n_configs']} configs ({report['elapsed_sec']} s) |",
        "| **Soft gate** | n≥40, NP>0, PF≥1.1, DD≤25% (develop). 1%/20% is **not** a gate. |",
        f"| **Hits** | develop eligible **{elig}** · soft **{soft}** · top-20 holdout soft **{ho}** |",
        f"| **2026 fired** | holdout n>0 on **{ho_n} / {report['n_configs']}** configs |",
        "| **promote / live_go** | **no / false** |",
        "| **Data** | FP native `H1.hc` via `read_mt5_hc`. H4 not used. Live terminal not touched. |",
        "",
        "Machine JSON: `results/btc_h1_range_vol_breakout_v1.json`.",
        "Predecessor: `btc_h1_trend_pullback_v1` (sealed; not retuned).",
        "",
        "---",
        "",
        "## Frozen before any develop metric",
        "",
        "| Choice | Lock |",
        "|--------|------|",
        "| Book | 0.01 lot · 250 pt slip · 4000 pt spread cap · commission 0 |",
        "| HTF / EMA | **Off** (v1 starve mode) |",
        "| Entry | Close-through of prior-N high/low after ATR squeeze + TR expand |",
        "| Fill | Next H1 open |",
        "| Weekend | Flatten Friday last (swap unmodeled) |",
        "| Split | UTC date < 2026-01-01 select; ≥ holdout |",
        "",
        "---",
        "",
        "## Screen",
        "",
    ]
    if best is None:
        lines.append("No trades in any config.")
    else:
        tag = "eligible best" if report.get("best_develop") else "best raw (not eligible)"
        lines.append(f"Best develop ({tag}): `{best['params']}`")
        lines.append("")
        lines.append("| Window | n | WR | PF | Net | DD | Median day |")
        lines.append("|--------|--:|---:|---:|----:|---:|-----------:|")
        lines.append(f"| Develop | {_row(best['develop'])} |")
        lines.append(f"| Holdout (from 2026-01-01) | {_row(best['holdout'])} |")
        lines.append("")
        d = best["develop"]
        h = best["holdout"]
        lines.append(
            f"soft_pass develop = **{str(d.get('soft_pass')).lower()}**. "
            f"Holdout n = **{h['trades']}** "
            f"(longs {h.get('longs', '?')}, shorts {h.get('shorts', '?')}). "
            "Median day % is diagnostic only — not a 1% gate."
        )
    lines += [
        "",
        f"**{soft} / {elig}** develop-eligible configs cleared the soft gate. "
        f"**{ho}** of the develop-ranked holdouts did. "
        f"Any-row holdout soft = **{int(report.get('n_holdout_soft_pass_any') or 0)}**. "
        "Holdout was not used for selection.",
        "",
        "---",
        "",
        "## Frozen grid (develop rank only; holdout is eval)",
        "",
        "| # | N | sq | exp | sl | Dev n | Dev PF | Dev NP | Dev soft | HO n | HO PF | HO NP | HO soft |",
        "|--:|--:|---:|----:|---:|------:|-------:|-------:|:--------:|-----:|------:|------:|:-------:|",
    ]
    for i, r in enumerate(report.get("grid") or []):
        p, d, h = r["params"], r["develop"], r["holdout"]
        pf_d = "inf" if d["profit_factor"] is None else f"{d['profit_factor']:.2f}"
        pf_h = "inf" if h["profit_factor"] is None else f"{h['profit_factor']:.2f}"
        lines.append(
            f"| {i} | {p['range_n']} | {p['squeeze_max']:.2f} | "
            f"{p['expand_min']:.2f} | {p['sl_atr']:.1f} | "
            f"{d['trades']} | {pf_d} | {d['net_pnl']:+.1f} | {d['soft_pass']} | "
            f"{h['trades']} | {pf_h} | {h['net_pnl']:+.1f} | {h['soft_pass']} |"
        )
    lines += [
        "",
        "DD% on $10k / 0.01 lot is a weak constraint (notional ~$650). "
        "Do not pick a new winner from the holdout columns. "
        "Do not retune these 16.",
        "",
        "---",
        "",
        "## What this does **not** authorize",
        "",
        "- Do not promote, `--live`, or attach an order EA.",
        "- Do not revive US100, XAU sealed families, Timescale, or M1.",
        "- Do not raise lots to 1.0 or cut slippage to 10 pt to chase 1%/20%.",
        "- Do not retune these 16 configs. A later idea is a **new** `search_id`.",
        "- Do not reopen `btc_h1_trend_pullback_v1` or add an EMA stack.",
        "- Do not edit `results/xau_loop_status.md` from this screen.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", type=Path, default=DATA_DIR / "history_BTCUSD_H1.csv")
    ap.add_argument("--cache", type=Path, default=FP_BTC_CACHE)
    ap.add_argument("--export-hc", action="store_true")
    ap.add_argument(
        "--json-out",
        type=Path,
        default=_ROOT / "results" / "btc_h1_range_vol_breakout_v1.json",
    )
    ap.add_argument(
        "--md-out",
        type=Path,
        default=_ROOT / "results" / "btc_h1_range_vol_breakout_v1.md",
    )
    args = ap.parse_args()
    lock = load_lock()
    if args.export_hc:
        files = export_btc_h1_csv(args.cache, DATA_DIR)
        print(f"exported {files}")
    if not args.h1.is_file():
        raise SystemExit(
            f"missing {args.h1}. Re-run with --export-hc "
            "(reads native .hc; does not kill terminal64)."
        )
    pending = ((lock.get("data") or {}).get("files") or {}).get("H1") or {}
    if pending.get("sha256") == "PENDING_EXPORT":
        raise SystemExit("lock data sha still PENDING_EXPORT — run --export-hc first")
    costs = frozen_cost_spec()
    report = run_search(args.h1, costs)
    write_slim_json(args.json_out, report)
    write_report_md(report, args.md_out)
    print(
        json.dumps(
            {
                "search_id": SEARCH_ID,
                "n_configs": report["n_configs"],
                "n_eligible": report["n_eligible"],
                "n_develop_soft_pass": report["n_develop_soft_pass"],
                "n_holdout_with_trades": report["n_holdout_with_trades"],
                "promote": False,
                "json": str(args.json_out),
                "md": str(args.md_out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
