#!/usr/bin/env python3
"""US100 v8 screen: H1 squeeze-breakout + H4 impulse fib pullback.

Lock: results/us_index_session_v8_lock.json
  select et_date < 2026-06-01
  holdout et_date >= 2026-07-01
  June 2026 is a burned buffer. July–August is cleaner, not virgin.

Leave M5 scalping. Hunt H1/H4 structural swings. Python-only.
Does not retune v1–v7. Does not use US30 / XAU / news / M1.
Costs keep 10 pt slippage/side. promote / live_go stay no.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
import time as pytime
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_autoresearch import (  # noqa: E402
    GOAL_DAILY_PCT,
    GOAL_MONTHLY_PCT,
    START_BALANCE,
    _et_arrays,
    pack_metrics,
    score_row,
)
from us_index_session_autoresearch_v4 import split_v4  # noqa: E402
from us_index_session_backtest import (  # noqa: E402
    CostSpec,
    costs_from_meta,
    hc_to_export_csv,
    load_m5_csv,
    parse_meta,
    read_mt5_hc,
)
from us_index_session_core import ATR_PERIOD, to_utc, wilder_atr  # noqa: E402
from us_index_session_htf import (  # noqa: E402
    fib_pullback_signals,
    h4_impulses,
    completed_daily_sma50_slope,
    simulate_htf_exits,
    squeeze_breakout_signals,
)

SEARCH_ID = "us_index_session_v8"
LOCK_PATH = _ROOT / "results" / "us_index_session_v8_lock.json"
SELECT_END = date(2026, 6, 1)
HOLDOUT_START = date(2026, 7, 1)

BB_K = (1.8, 2.0)
KC_MULT = (1.25, 1.5)
ONE_PER_DAY = (True, False)
FLATTEN_FRIDAY = (True, False)
IMPULSE_K = (2.0, 2.5)
ENTRIES = ("close_in_zone", "wick_touch")
PIVOTS = ((3, 2), (5, 5))

FP_US100_CACHE = (
    Path.home()
    / ".mt5-fpmarkets"
    / "drive_c"
    / "Program Files"
    / "FP Markets MT5 Terminal"
    / "Bases"
    / "FPMarketsSC-Live"
    / "history"
    / "US100"
    / "cache"
)


def build_grid() -> list[dict]:
    rows: list[dict] = []
    for bk, km, opd, flat in itertools.product(BB_K, KC_MULT, ONE_PER_DAY, FLATTEN_FRIDAY):
        rows.append(
            {
                "family": "h1_volatility_squeeze_breakout",
                "bb_k": bk,
                "kc_atr_mult": km,
                "one_per_day": opd,
                "flatten_friday": flat,
                "exit": "atr_sl1.0_tp2.0",
            }
        )
    for k, entry, flat, (left, right) in itertools.product(
        IMPULSE_K, ENTRIES, FLATTEN_FRIDAY, PIVOTS
    ):
        rows.append(
            {
                "family": "h4_impulse_fib_pullback",
                "impulse_k": k,
                "entry": entry,
                "flatten_friday": flat,
                "pivot_left": left,
                "pivot_right": right,
                "one_per_impulse": True,
                "exit": "origin_sl0.5atr_tp_extreme",
            }
        )
    return rows


def _slim(cfg: dict) -> dict:
    return dict(cfg)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_htf_csvs(
    cache_dir: Path, out_dir: Path, symbol: str = "US100"
) -> dict[str, dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, dict] = {}
    for tf, name in (("H1", "H1.hc"), ("H4", "H4.hc"), ("Daily", "Daily.hc")):
        src = cache_dir / name
        csv = out_dir / f"history_{symbol}_{tf}.csv"
        hc_to_export_csv(src, csv, symbol, tf=tf)
        df = read_mt5_hc(src)
        meta[tf] = {
            "path": str(csv.relative_to(_ROOT)),
            "sha256": _sha256(csv),
            "bars": int(len(df)),
        }
    return meta


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
    sl_price: np.ndarray | None,
    tp_price: np.ndarray | None,
) -> dict:
    trades = simulate_htf_exits(
        times,
        open_,
        high,
        low,
        spread,
        sigs,
        costs,
        sl_price=sl_price,
        tp_price=tp_price,
        atr=atr,
        sl_mult=1.0,
        tp_mult=2.0,
        flatten_friday=bool(cfg["flatten_friday"]),
        dow=dow,
    )
    pre, post = split_v4(trades)
    return {
        "params": _slim(cfg),
        "develop": pack_metrics(pre),
        "holdout": pack_metrics(post),
        "develop_score": score_row(pack_metrics(pre)),
    }


def run_search(
    h1_csv: Path,
    h4_csv: Path,
    daily_csv: Path,
    meta_path: Path | None,
    costs: CostSpec,
) -> dict:
    meta = parse_meta(meta_path) if meta_path and meta_path.is_file() else {}
    offset = int(float(meta.get("server_utc_offset_sec") or 10800))
    h1 = load_m5_csv(h1_csv, offset)
    h4 = load_m5_csv(h4_csv, offset)
    daily = load_m5_csv(daily_csv, offset)

    times = [to_utc(ts.to_pydatetime()) for ts in h1["time_utc"]]
    high = h1["high"].to_numpy(float)
    low = h1["low"].to_numpy(float)
    close = h1["close"].to_numpy(float)
    open_ = h1["open"].to_numpy(float)
    spread = h1["spread"].to_numpy(float)
    mins, keys, dow, _ny = _et_arrays(times)
    atr14 = wilder_atr(high, low, close, ATR_PERIOD)

    h4_times = [to_utc(ts.to_pydatetime()) for ts in h4["time_utc"]]
    h4_high = h4["high"].to_numpy(float)
    h4_low = h4["low"].to_numpy(float)
    h4_close = h4["close"].to_numpy(float)
    h4_atr = wilder_atr(h4_high, h4_low, h4_close, ATR_PERIOD)

    d_times = [to_utc(ts.to_pydatetime()) for ts in daily["time_utc"]]
    d_close = daily["close"].to_numpy(float)
    slope = completed_daily_sma50_slope(times, d_times, d_close)

    impulse_cache: dict[tuple[int, int, float], list] = {}
    for left, right in PIVOTS:
        for k in IMPULSE_K:
            impulse_cache[(left, right, k)] = h4_impulses(
                h4_high, h4_low, h4_close, h4_times, h4_atr, left=left, right=right, k=k
            )

    grid = build_grid()
    rows: list[dict] = []
    t0 = pytime.time()
    for i, cfg in enumerate(grid):
        fam = cfg["family"]
        if fam == "h1_volatility_squeeze_breakout":
            sigs = squeeze_breakout_signals(
                close,
                high,
                low,
                mins,
                keys,
                dow,
                slope,
                bb_k=float(cfg["bb_k"]),
                kc_atr_mult=float(cfg["kc_atr_mult"]),
                one_per_day=bool(cfg["one_per_day"]),
            )
            sl_p = tp_p = None
        else:
            imps = impulse_cache[
                (int(cfg["pivot_left"]), int(cfg["pivot_right"]), float(cfg["impulse_k"]))
            ]
            sigs, sl_p, tp_p = fib_pullback_signals(
                close,
                high,
                low,
                times,
                mins,
                dow,
                imps,
                entry=str(cfg["entry"]),
            )
        row = _run(cfg, times, open_, high, low, atr14, spread, dow, costs, sigs, sl_p, tp_p)
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
    top20 = ranked[:20]
    n_hit = sum(1 for r in eligible if r["develop"]["goal_both"])
    n_ho = sum(1 for r in top20 if r["holdout"]["goal_both"])
    by_fam: dict[str, dict] = {}
    fam_rank = sorted(
        rows,
        key=lambda r: (
            r["develop"]["profit_factor"] or 0.0,
            r["develop"]["expectancy"],
            r["develop"]["trades"],
        ),
        reverse=True,
    )
    for pool in (ranked, fam_rank):
        for r in pool:
            fam = r["params"]["family"]
            if fam not in by_fam:
                by_fam[fam] = r
    elig_by_fam = {
        fam: sum(1 for r in eligible if r["params"]["family"] == fam)
        for fam in {r["params"]["family"] for r in rows}
    }
    return {
        "search_id": SEARCH_ID,
        "promote": False,
        "live_go": False,
        "python_only": True,
        "selection_end": str(SELECT_END),
        "holdout_start": str(HOLDOUT_START),
        "start_balance": START_BALANCE,
        "goal_daily_pct": GOAL_DAILY_PCT,
        "goal_monthly_pct": GOAL_MONTHLY_PCT,
        "n_configs": len(rows),
        "n_eligible": len(eligible),
        "n_eligible_develop": len(eligible),
        "n_eligible_by_family": elig_by_fam,
        "n_develop_hit_goal": n_hit,
        "n_top20_holdout_hit_goal": n_ho,
        "elapsed_sec": round(elapsed, 2),
        "costs": asdict(costs),
        "bars_h1": int(len(h1)),
        "bars_h4": int(len(h4)),
        "bars_daily": int(len(daily)),
        "from": str(h1["time_utc"].iloc[0]) if len(h1) else "",
        "to": str(h1["time_utc"].iloc[-1]) if len(h1) else "",
        "data_source": "FP native H1.hc / H4.hc / Daily.hc via read_mt5_hc",
        "best_develop": best,
        "best_raw_develop": fam_rank[0] if fam_rank else None,
        "best_by_family": by_fam,
        "top20": top20,
        "note": (
            "New search. Leave M5. H1 squeeze release + prior Donchian + "
            "completed Daily SMA50. H4 impulse via htf_fib_core pivots, "
            "H1 golden-pocket fill. July–August holdout already sat in "
            "v4–v7 aggregates — cleaner, not virgin. promote=no."
        ),
    }


def write_report_md(report: dict, path: Path) -> None:
    best = report.get("best_develop") or report.get("best_raw_develop")
    elig = int(report["n_eligible_develop"])
    hit = int(report["n_develop_hit_goal"])
    ho = int(report["n_top20_holdout_hit_goal"])
    by = report.get("n_eligible_by_family") or {}
    fams = report.get("best_by_family") or {}

    def _row(m: dict) -> str:
        pf = m.get("profit_factor")
        pf_s = "inf" if pf is None else f"{pf:.2f}"
        return (
            f"{m['trades']} | {100.0 * m['win_rate']:.0f}% | {pf_s} | "
            f"**{100.0 * m['median_daily_pct']:+.2f}%** | "
            f"**{100.0 * m['median_monthly_pct']:+.2f}%**"
        )

    lines = [
        "# US100 v8 screen (`us_index_session_v8`)",
        "",
        "| Field | Value |",
        "|-------|--------|",
        "| **Date** | 2026-08-18 |",
        "| **Search** | `us_index_session_v8` — H1 squeeze-breakout + H4 impulse fib pullback |",
        "| **Lock** | `results/us_index_session_v8_lock.json` |",
        "| **Select** | `et_date < 2026-06-01` |",
        "| **Holdout** | **2026-07-01** onward. June unused (burned). July–August already sat inside the v4–v7 holdout aggregates — cleaner window, **not virgin**. |",
        "| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |",
        f"| **Grid** | {report['n_configs']} configs (16 squeeze + 16 fib; {report['elapsed_sec']} s) |",
        "| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |",
        f"| **Hits** | develop **{hit} / {elig}** eligible · top-20 holdout **{ho} / {len(report.get('top20') or [])}** |",
        f"| **Eligible by family** | `h1_volatility_squeeze_breakout` **{by.get('h1_volatility_squeeze_breakout', 0)}** · `h4_impulse_fib_pullback` **{by.get('h4_impulse_fib_pullback', 0)}** |",
        "| **promote / live_go** | **no / false** |",
        "| **Data** | FP native `H1.hc` / `H4.hc` / `Daily.hc` via `read_mt5_hc`. Not the M5 request-file dump. Live terminal not touched. |",
        "",
        "Machine JSON: `results/us_index_session_v8.json`.",
        "",
        "Leave M5 scalping. Not a retune. Not an XAU charter. These families stay **Python-only**.",
        "",
        "---",
        "",
        "## Frozen before any develop metric",
        "",
        "| Choice | Lock |",
        "|--------|------|",
        "| Grid | 32 configs locked before peek (16 + 16). |",
        "| Squeeze | BB inside KC on **completed** H1. Trade only on release. |",
        "| Donchian | Channel from `i-20..i-1`. Close[i] vs that. Never same-bar high. |",
        "| Daily SMA50 | Completed Daily only (today's D1 forming). Rising → longs; falling → shorts. |",
        "| Pivots | `htf_fib_core.confirmed_pivots` (not re-derived). |",
        "| Fill | Next H1 open. H4 confirm close = H4 open + 4h. |",
        "| Friday | No new weekend gap (Friday last H1). Optional flatten at that open. |",
        "",
        "---",
        "",
        "## Goals",
        "",
    ]
    if best is None:
        lines.append("No trades in any config.")
    else:
        tag = "eligible best" if report.get("best_develop") else "best raw (not eligible)"
        lines.append(f"Best develop ({tag}): `{best['params']}`")
        lines.append("")
        lines.append("| Window | n | WR | PF | Median day | Median month |")
        lines.append("|--------|--:|---:|---:|-----------:|-------------:|")
        lines.append(f"| Develop | {_row(best['develop'])} |")
        lines.append(f"| Holdout (from 2026-07-01) | {_row(best['holdout'])} |")
        lines.append("")
    lines.append("| Family | Eligible | Best develop | Holdout |")
    lines.append("|--------|----------|--------------|---------|")
    for fam in ("h1_volatility_squeeze_breakout", "h4_impulse_fib_pullback"):
        r = fams.get(fam)
        if r is None:
            lines.append(f"| {fam} | 0 | — | — |")
            continue
        d, h = r["develop"], r["holdout"]
        pf_d = "inf" if d["profit_factor"] is None else f"{d['profit_factor']:.2f}"
        pf_h = "inf" if h["profit_factor"] is None else f"{h['profit_factor']:.2f}"
        lines.append(
            f"| {fam} | {by.get(fam, 0)} / 16 | "
            f"{d['trades']} trades · PF {pf_d} · **{100.0 * d['median_daily_pct']:+.2f}%** day | "
            f"{h['trades']} trades · PF {pf_h} · **{100.0 * h['median_daily_pct']:+.2f}%** day |"
        )
    lines += [
        "",
        f"**{hit} / {elig}** develop-eligible configs hit both 1% and 20%. "
        f"**{ho}** of the ranked holdouts did either. There is no promote path.",
        "",
        "---",
        "",
        "## What this does **not** authorize",
        "",
        "- Do not promote, `--live`, or attach an order EA.",
        "- Do not put v8 on the overlay.",
        "- Do not revive M5 families, US30, XAU, news-drift, Timescale, or M1.",
        "- Do not cut slippage or raise lots.",
        "- Do not retune these 32 configs. A later idea is a **new** `search_id`.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--h1",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "history_US100_H1.csv",
    )
    ap.add_argument(
        "--h4",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "history_US100_H4.csv",
    )
    ap.add_argument(
        "--daily",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "history_US100_Daily.csv",
    )
    ap.add_argument(
        "--meta",
        type=Path,
        default=_ROOT / "results" / "us_index_data" / "symbol_meta_US100.csv",
    )
    ap.add_argument(
        "--cache",
        type=Path,
        default=FP_US100_CACHE,
    )
    ap.add_argument("--out", type=Path, default=_ROOT / "results" / "us_index_session_v8.json")
    ap.add_argument(
        "--md", type=Path, default=_ROOT / "results" / "us_index_session_v8.md"
    )
    args = ap.parse_args()
    lock = json.loads(LOCK_PATH.read_text())
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit("search_id mismatch")
    if lock.get("selection_end") != "2026-06-01" or lock.get("holdout_start") != "2026-07-01":
        raise SystemExit("holdout/selection lock mismatch")
    if lock.get("causality", {}).get("donchian_include_i") is not False:
        raise SystemExit("donchian_include_i must be frozen false")
    if lock.get("causality", {}).get("daily_sma50_uses_forming") is not False:
        raise SystemExit("daily_sma50_uses_forming must be frozen false")
    grid = build_grid()
    if len(grid) != int(lock["n_configs_expected"]):
        raise SystemExit(f"grid {len(grid)} != lock {lock['n_configs_expected']}")
    data_dir = args.h1.parent
    if args.cache.is_dir():
        export_htf_csvs(args.cache, data_dir)
    lock_files = lock.get("data", {}).get("files", {})
    for tf, path in (("H1", args.h1), ("H4", args.h4), ("Daily", args.daily)):
        if not path.is_file():
            raise SystemExit(f"missing {path}")
        want = (lock_files.get(tf) or {}).get("sha256")
        if want and _sha256(path) != want:
            raise SystemExit(f"sha256 mismatch for {tf}: rewrite the lock, do not peek")
    meta = parse_meta(args.meta) if args.meta.is_file() else {}
    costs = costs_from_meta(
        meta, lots=1.0, slippage_points=10.0, commission_per_lot=0.0, max_spread_points=200.0
    )
    report = run_search(args.h1, args.h4, args.daily, args.meta, costs)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    write_report_md(report, args.md)
    best = report["best_develop"] or report["best_raw_develop"]
    print(
        json.dumps(
            {
                "n_configs": report["n_configs"],
                "n_eligible": report["n_eligible"],
                "n_eligible_develop": report["n_eligible_develop"],
                "n_develop_hit_goal": report["n_develop_hit_goal"],
                "n_top20_holdout_hit_goal": report["n_top20_holdout_hit_goal"],
                "elapsed_sec": report["elapsed_sec"],
                "best_develop_params": None if best is None else best["params"],
                "best_develop": None if best is None else best["develop"],
                "best_holdout": None if best is None else best["holdout"],
                "best_by_family": {
                    k: {
                        "params": v["params"],
                        "develop_day": v["develop"]["median_daily_pct"],
                        "holdout_day": v["holdout"]["median_daily_pct"],
                        "develop_trades": v["develop"]["trades"],
                        "develop_pf": v["develop"]["profit_factor"],
                    }
                    for k, v in report["best_by_family"].items()
                },
                "promote": False,
            },
            indent=2,
        )
    )
    print(f"wrote {args.out}")
    print(f"wrote {args.md}")


if __name__ == "__main__":
    main()
