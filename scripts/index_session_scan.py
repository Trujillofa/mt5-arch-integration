#!/usr/bin/env python3
"""Scan frozen ``ny_cash_orb_vwap_ema_flat`` across available index M5 tapes.

Lock (``results/index_session_scan/lock.json``) is written first and is the
only ranking contract: develop PF after costs, n floor, max DD. Holdout
``2026-06-01`` is evaluation-only (index v1 split — not the XAU lock).

SAFETY: offline research. promote / live_go = no. Does not retune
GoldSessionScalp or the archived v1–v8 families. No live orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_backtest import (  # noqa: E402
    FAMILY_ID,
    HOLDOUT_START,
    CostSpec,
    hc_to_export_csv,
    infer_hc_tf,
    read_mt5_hc,
    refuse_mutated_frozen_book,
    require_frozen_cost_book,
    run_file,
    slim_committed_report,
    write_slim_json,
)
from us_index_session_core import looks_like_us_index  # noqa: E402

LOCK_PATH = _ROOT / "results" / "index_session_scan" / "lock.json"
OUT_DIR = _ROOT / "results" / "index_session_scan"
DATA_DIR = OUT_DIR / "data"
SEARCH_ID = "index_session_scan_v1"
OFFSET_CANDIDATES = (0, 7200, 10800)

WINE_M5 = (
    {
        "symbol": "US100",
        "broker": "fpmarkets",
        "path": Path.home()
        / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal"
        / "Bases/FPMarketsSC-Live/history/US100/cache/M5.hc",
        "default_offset": 10800,
    },
    {
        "symbol": "US30",
        "broker": "fpmarkets",
        "path": Path.home()
        / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal"
        / "Bases/FPMarketsSC-Live/history/US30/cache/M5.hc",
        "default_offset": 10800,
    },
    {
        "symbol": "DJ30.r",
        "broker": "vantage",
        "path": Path.home()
        / ".mt5-vantage/drive_c/Program Files/Vantage International MT5"
        / "Bases/VantageMarkets-Live 5/history/DJ30.r/cache/M5.hc",
        "default_offset": 10800,
    },
    {
        "symbol": "US30m",
        "broker": "exness",
        "path": Path.home()
        / ".mt5-exness/drive_c/Program Files/MetaTrader 5 EXNESS"
        / "Bases/Exness-MT5Real11/history/US30m/cache/M5.hc",
        "default_offset": 0,
    },
)

WRONG_TF = (
    {
        "symbol": "NAS100.r",
        "broker": "vantage",
        "tf": "M15",
        "reason": "M15 cannot stamp a 15-minute NY OR without inventing M5 bars",
        "path": Path.home()
        / ".mt5-vantage/drive_c/Program Files/Vantage International MT5"
        / "Bases/VantageMarkets-Live 5/history/NAS100.r/cache/M15.hc",
    },
    {
        "symbol": "US500",
        "broker": "fpmarkets",
        "tf": "H1",
        "reason": "H1 cannot represent the 15-minute NY cash OR",
        "path": Path.home()
        / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal"
        / "Bases/FPMarketsSC-Live/history/US500/cache/H1.hc",
    },
)

EMPTY_WINE = (
    ("wsf", "DJ30.c"),
    ("ftmo", "US30.cash"),
    ("alphacapital", "US30.pro"),
    ("fundednext", "US30"),
    ("fortraders", "US30"),
    ("neomaa", "US30"),
)

DUKAS_US_CASH = (
    ("usa30idxusd", "US30"),
    ("usa500idxusd", "US500"),
    ("usatechidxusd", "US100"),
    ("ussc2000idxusd", "US2000"),
)
DUKAS_OTHER = (
    ("deuidxeur", "GER40"),
    ("gbridxgbp", "UK100"),
    ("jpnidxjpy", "JP225"),
    ("ausidxaud", "AU200"),
    ("eusidxeur", "EU50"),
    ("fraidxeur", "FRA40"),
    ("cheidxchf", "SUI20"),
    ("hkgidxhkd", "HK50"),
    ("espidxeur", "ESP35"),
    ("nldidxeur", "NL25"),
    ("itaidxeur", "IT40"),
    ("chiidxusd", "CHINA50"),
)

CLOCK_NOTE = {
    "GER40": "Xetra 09:00 Europe/Berlin — not NY cash 09:30",
    "UK100": "LSE 08:00 Europe/London — not NY cash 09:30",
    "JP225": "TSE 09:00 Asia/Tokyo — not NY cash 09:30",
    "AU200": "ASX 10:00 Australia/Sydney — not NY cash 09:30",
    "EU50": "European cash open (~09:00 Europe/Berlin) — not NY cash 09:30",
    "FRA40": "Euronext Paris 09:00 Europe/Paris — not NY cash 09:30",
    "SUI20": "SIX 09:00 Europe/Zurich — not NY cash 09:30",
    "HK50": "HKEX 09:30 Asia/Hong_Kong — not NY 09:30 ET",
    "ESP35": "Bolsa Madrid 09:00 Europe/Madrid — not NY cash 09:30",
    "NL25": "Euronext Amsterdam 09:00 Europe/Amsterdam — not NY cash 09:30",
    "IT40": "Borsa Italiana 09:00 Europe/Rome — not NY cash 09:30",
    "CHINA50": "China A50 09:30 Asia/Shanghai — not NY 09:30 ET",
}


def load_lock(path: Path = LOCK_PATH) -> dict:
    if not path.is_file():
        raise SystemExit(f"lock missing (must be written first): {path}")
    lock = json.loads(path.read_text())
    refuse_frictionless_lock(lock)
    refuse_mutated_frozen_book(lock)
    if lock.get("search_id") != SEARCH_ID:
        raise SystemExit(f"lock search_id must be {SEARCH_ID}")
    if str(lock.get("holdout_start")) != str(HOLDOUT_START):
        raise SystemExit("lock holdout_start must match index v1 2026-06-01")
    return lock


def refuse_frictionless_lock(lock: dict) -> None:
    """Refuse a lock or cost book that turns costs off."""
    costs = lock.get("costs") if isinstance(lock.get("costs"), dict) else {}
    if lock.get("frictionless") is True or costs.get("frictionless") is True:
        raise SystemExit("frictionless refused")
    slip = costs.get("slippage_points")
    if slip is None or float(slip) == 0.0:
        raise SystemExit("frictionless refused: slippage_points must be 10")
    if float(slip) != 10.0:
        raise SystemExit("frozen book slippage_points must be 10")
    assumed = costs.get("assumed_spread_when_unmeasured")
    if assumed is not None and float(assumed) <= 0.0:
        raise SystemExit("frictionless refused: assumed spread must be > 0")


def costs_from_lock(lock: dict, *, spread_unmeasured: bool) -> CostSpec:
    c = lock["costs"]
    spec = CostSpec(
        point_size=float(c["point_size"]),
        contract_size=float(c["contract_size"]),
        lots=float(c["lots"]),
        commission_per_lot=float(c["commission_per_lot"]),
        slippage_points=float(c["slippage_points"]),
        max_spread_points=float(c["max_spread_points"]),
    )
    require_frozen_cost_book(spec)
    if spread_unmeasured and float(c["assumed_spread_when_unmeasured"]) <= 0:
        raise SystemExit("frictionless refused: unmeasured spread is 0")
    return spec


def session_fit(symbol: str) -> tuple[str, str]:
    if looks_like_us_index(symbol):
        return "us_cash_0930", "NY cash 09:30 America/New_York"
    note = CLOCK_NOTE.get(symbol, "non-US cash open — wrong event for this model")
    return "other_cash_open", note


def pin_pf(pf: float | None) -> float:
    return 3.0 if pf is None else float(pf)


def rank_scan_rows(rows: list[dict], lock: dict) -> list[dict]:
    """Rank by develop PF / max DD / expectancy. Holdout keys are ignored."""
    n_floor = int(lock.get("n_floor") or lock["score"]["n_floor"])
    eligible = []
    for row in rows:
        dev = row.get("develop") or {}
        if int(dev.get("trades") or 0) < n_floor:
            continue
        eligible.append(row)
    return sorted(
        eligible,
        key=lambda r: (
            pin_pf(r["develop"].get("profit_factor")),
            float(r["develop"].get("max_dd") or 0.0),
            float(r["develop"].get("expectancy") or 0.0),
        ),
        reverse=True,
    )


def trade_candidates(ranked: list[dict]) -> list[dict]:
    return [r for r in ranked if r.get("session_fit") == "us_cash_0930"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def infer_server_offset(hc_path: Path, default: int) -> dict:
    """Pick UTC offset by NY 09:30 volume spike — clock only, not PnL."""
    from datetime import time
    from zoneinfo import ZoneInfo

    df = read_mt5_hc(hc_path)
    tz = ZoneInfo("America/New_York")
    best = (float("-inf"), int(default))
    scores = {}
    for off in OFFSET_CANDIDATES:
        utc = pd.to_datetime(df["server_epoch"], unit="s", utc=True)
        utc = utc - pd.to_timedelta(int(off), unit="s")
        et = utc.dt.tz_convert(tz)
        t = et.dt.time
        cash = (t >= time(9, 30)) & (t < time(10, 0))
        pre = (t >= time(3, 0)) & (t < time(9, 0))
        vc = float(df.loc[cash, "tick_volume"].median()) if bool(cash.any()) else 0.0
        vp = float(df.loc[pre, "tick_volume"].median()) if bool(pre.any()) else 0.0
        ratio = vc / vp if vp > 0 else vc
        scores[str(off)] = {"cash_med": vc, "pre_med": vp, "ratio": ratio}
        if ratio > best[0]:
            best = (ratio, int(off))
    return {"offset_sec": best[1], "scores": scores, "default": int(default)}


def write_meta(
    path: Path,
    *,
    symbol: str,
    source: str,
    offset: int,
    spread_source: str,
    extra: dict | None = None,
) -> Path:
    rows = {
        "requested": symbol,
        "resolved": symbol,
        "digits": "2",
        "point": "0.01",
        "contract_size": "1.0",
        "server_utc_offset_sec": str(int(offset)),
        "tf": "M5",
        "source": source,
        "spread_source": spread_source,
    }
    if extra:
        rows.update({k: str(v) for k, v in extra.items()})
    body = "key,value\n" + "".join(f"{k},{v}\n" for k, v in rows.items())
    path.write_text(body)
    return path


def dukas_to_export(src: Path, dest: Path, symbol: str, assumed_spread: float) -> Path:
    raw = pd.read_csv(src)
    if "timestamp" not in raw.columns:
        raise SystemExit(f"dukascopy csv missing timestamp: {src}")
    epoch = (pd.to_numeric(raw["timestamp"], errors="coerce") / 1000.0).astype(np.int64)
    ts = pd.to_datetime(epoch, unit="s", utc=True)
    out = pd.DataFrame(
        {
            "time": ts.dt.strftime("%Y.%m.%d %H:%M"),
            "tf": "M5",
            "symbol": symbol,
            "server_epoch": epoch,
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "tick_volume": pd.to_numeric(raw.get("volume", 1.0), errors="coerce").fillna(
                1.0
            ),
            "spread": float(assumed_spread),
        }
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False)
    return dest


def _metrics_block(report: dict, key: str) -> dict:
    raw = report.get(key) or {}
    keep = (
        "trades",
        "wins",
        "losses",
        "win_rate",
        "net_pnl",
        "avg_trade",
        "profit_factor",
        "max_dd",
        "expectancy",
        "longs",
        "shorts",
    )
    return {k: raw.get(k) for k in keep}


def run_symbol(
    *,
    row_id: str,
    symbol: str,
    csv_path: Path,
    meta_path: Path,
    lock: dict,
    source: str,
    spread_source: str,
    spread_unmeasured: bool,
) -> dict:
    costs = costs_from_lock(lock, spread_unmeasured=spread_unmeasured)
    holdout = date.fromisoformat(str(lock["holdout_start"]))
    report = run_file(csv_path, meta_path, costs=costs, holdout_start=holdout)
    fit, fit_note = session_fit(symbol)
    n_floor = int(lock["n_floor"])
    develop = _metrics_block(report, "pre_holdout")
    holdout_m = _metrics_block(report, "holdout")
    all_m = _metrics_block(report, "all")
    eligible = int(develop.get("trades") or 0) >= n_floor
    return {
        "id": row_id,
        "symbol": symbol,
        "family_id": FAMILY_ID,
        "source": source,
        "spread_source": spread_source,
        "spread_unmeasured": spread_unmeasured,
        "slippage_unmeasured": True,
        "session_fit": fit,
        "session_note": fit_note,
        "bars": report.get("bars"),
        "from": report.get("from"),
        "to": report.get("to"),
        "signals": report.get("signals"),
        "costs": asdict(costs),
        "develop": develop,
        "holdout": holdout_m,
        "all": all_m,
        "eligible": eligible,
        "trade_candidate": eligible and fit == "us_cash_0930",
        "promote": False,
        "live_go": False,
        "csv": str(csv_path.relative_to(_ROOT)) if csv_path.is_relative_to(_ROOT) else str(csv_path),
    }


def collect_wine(lock: dict) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    manifest: list[dict] = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for spec in WINE_M5:
        src = Path(spec["path"])
        if not src.is_file():
            manifest.append(
                {
                    "id": f"{spec['broker']}_{spec['symbol']}",
                    "status": "missing",
                    "path": str(src),
                }
            )
            continue
        clock = infer_server_offset(src, int(spec["default_offset"]))
        offset = int(clock["offset_sec"])
        stem = f"history_{spec['broker']}_{spec['symbol'].replace('.', '_')}_M5"
        csv_path = DATA_DIR / f"{stem}.csv"
        if not csv_path.is_file():
            hc_to_export_csv(src, csv_path, spec["symbol"], "M5")
        meta_path = DATA_DIR / f"symbol_meta_{spec['broker']}_{spec['symbol'].replace('.', '_')}.csv"
        write_meta(
            meta_path,
            symbol=spec["symbol"],
            source=str(src),
            offset=offset,
            spread_source="wine_hc_tape",
            extra={"broker": spec["broker"], "clock": json.dumps(clock)},
        )
        df = read_mt5_hc(src)
        manifest.append(
            {
                "id": f"{spec['broker']}_{spec['symbol']}",
                "symbol": spec["symbol"],
                "broker": spec["broker"],
                "tf": infer_hc_tf(df["server_epoch"].to_numpy()),
                "source_kind": "wine_hc",
                "path": str(src),
                "extract": str(csv_path),
                "sha256": sha256_file(src),
                "bars": int(len(df)),
                "from": str(pd.to_datetime(int(df.server_epoch.iloc[0]), unit="s", utc=True)),
                "to": str(pd.to_datetime(int(df.server_epoch.iloc[-1]), unit="s", utc=True)),
                "spread_median": float(df["spread"].median()),
                "server_utc_offset_sec": offset,
                "clock": clock,
            }
        )
        rows.append(
            run_symbol(
                row_id=f"{spec['broker']}_{spec['symbol']}",
                symbol=spec["symbol"],
                csv_path=csv_path,
                meta_path=meta_path,
                lock=lock,
                source=f"wine:{spec['broker']}:{src}",
                spread_source="wine_hc_tape",
                spread_unmeasured=False,
            )
        )
    return rows, manifest


def collect_dukas(lock: dict) -> tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    manifest: list[dict] = []
    assumed = float(lock["costs"]["assumed_spread_when_unmeasured"])
    min_bars = int(lock.get("min_bars_m5") or 2000)
    for instrument, symbol in (*DUKAS_US_CASH, *DUKAS_OTHER):
        raw = DATA_DIR / f"history_{symbol}_dukascopy_M5.csv"
        row_id = f"dukascopy_{symbol}"
        if not raw.is_file():
            manifest.append(
                {
                    "id": row_id,
                    "status": "missing",
                    "instrument": instrument,
                    "symbol": symbol,
                }
            )
            continue
        export = DATA_DIR / f"export_{symbol}_dukascopy_M5.csv"
        dukas_to_export(raw, export, symbol, assumed)
        n = int(sum(1 for _ in export.open()) - 1)
        if n < min_bars:
            manifest.append(
                {
                    "id": row_id,
                    "status": "insufficient_bars",
                    "instrument": instrument,
                    "symbol": symbol,
                    "bars": n,
                    "min_bars_m5": min_bars,
                    "sha256": sha256_file(raw),
                    "path": str(raw),
                }
            )
            continue
        meta_path = DATA_DIR / f"symbol_meta_dukascopy_{symbol}.csv"
        write_meta(
            meta_path,
            symbol=symbol,
            source=str(raw),
            offset=0,
            spread_source=f"assumed_{assumed:g}_unmeasured",
            extra={"instrument": instrument, "dukascopy_utc": "1"},
        )
        raw_df = pd.read_csv(raw, usecols=["timestamp"])
        t0 = pd.to_datetime(int(raw_df.timestamp.iloc[0]), unit="ms", utc=True)
        t1 = pd.to_datetime(int(raw_df.timestamp.iloc[-1]), unit="ms", utc=True)
        manifest.append(
            {
                "id": row_id,
                "symbol": symbol,
                "instrument": instrument,
                "tf": "M5",
                "source_kind": "dukascopy_public_bars",
                "path": str(raw),
                "sha256": sha256_file(raw),
                "bars": int(len(raw_df)),
                "from": str(t0),
                "to": str(t1),
                "spread": assumed,
                "spread_unmeasured": True,
                "server_utc_offset_sec": 0,
            }
        )
        rows.append(
            run_symbol(
                row_id=row_id,
                symbol=symbol,
                csv_path=export,
                meta_path=meta_path,
                lock=lock,
                source=f"dukascopy:{instrument}",
                spread_source=f"assumed_{assumed:g}_unmeasured",
                spread_unmeasured=True,
            )
        )
    return rows, manifest


def gaps() -> list[dict]:
    out = [
        {
            "symbol": spec["symbol"],
            "broker": spec["broker"],
            "tf": spec["tf"],
            "reason": spec["reason"],
            "path": str(spec["path"]),
            "exists": spec["path"].is_file(),
        }
        for spec in WRONG_TF
    ]
    for broker, symbol in EMPTY_WINE:
        out.append(
            {
                "symbol": symbol,
                "broker": broker,
                "tf": None,
                "reason": "Wine history folder empty (no M5 bars)",
                "exists": False,
            }
        )
    return out


def write_analysis(
    path: Path, lock: dict, ranked: list[dict], rows: list[dict], top: dict | None
) -> None:
    lines = [
        "# Index session scan — frozen NY cash 09:30 OR model",
        "",
        "| Field | Value |",
        "|-------|--------|",
        f"| **Date** | {lock['locked_at']} |",
        f"| **Search** | `{lock['search_id']}` |",
        f"| **Family** | `{FAMILY_ID}` (unmodified) |",
        f"| **Holdout** | `{lock['holdout_start']}` evaluate-only (index v1, not XAU) |",
        "| **Score** | develop PF after costs; n≥40; max DD then expectancy |",
        "| **Costs** | tape spread (or assumed 60 unmeasured) + 10 pt slip/side + $0 commission |",
        "| **promote / live_go** | **no / false** |",
        "",
        "Not a retune. GoldSessionScalp untouched. Goal remains archived; this scan does not promote.",
        "",
        "## Ranking (develop only)",
        "",
        "Holdout metrics are shown but were **not** used to order rows.",
        "",
        "| Rank | id | fit | n | WR | PF | net | max DD | holdout PF | note |",
        "|-----:|----|-----|--:|---:|---:|----:|-------:|-----------:|------|",
    ]
    for i, r in enumerate(ranked, 1):
        d = r["develop"]
        ho = r["holdout"]
        pf = d.get("profit_factor")
        hopf = ho.get("profit_factor")
        lines.append(
            "| {rank} | `{id}` | {fit} | {n} | {wr:.1%} | {pf} | {net:.1f} | {dd:.1f} | {hopf} | {note} |".format(
                rank=i,
                id=r["id"],
                fit=r["session_fit"],
                n=int(d.get("trades") or 0),
                wr=float(d.get("win_rate") or 0.0),
                pf="∞" if pf is None else f"{float(pf):.2f}",
                net=float(d.get("net_pnl") or 0.0),
                dd=float(d.get("max_dd") or 0.0),
                hopf="—" if hopf is None and not ho.get("trades") else (
                    "∞" if hopf is None else f"{float(hopf):.2f}"
                ),
                note=("trade-candidate" if r.get("trade_candidate") else r["session_note"][:40]),
            )
        )
    skipped = [r for r in rows if not r.get("eligible")]
    if skipped:
        lines += ["", "## Below n floor / ineligible", ""]
        for r in skipped:
            d = r["develop"]
            lines.append(
                f"- `{r['id']}` develop n={d.get('trades')} fit={r['session_fit']} "
                f"— {r['session_note']}"
            )
    lines += ["", "## Most suitable to trade", ""]
    if top is None:
        lines.append(
            "No US-cash tape met the locked n floor after costs. "
            "**promote=no.** Overlay only."
        )
    else:
        d = top["develop"]
        pf = d.get("profit_factor")
        pf_s = "∞" if pf is None else f"{float(pf):.2f}"
        lines.append(
            f"**`{top['id']}`** ({top['symbol']}) — session fit `{top['session_fit']}`, "
            f"develop PF {pf_s}, n={d.get('trades')}, max DD {d.get('max_dd')}."
        )
        lines.append("")
        if pin_pf(pf) < 1.0:
            lines.append(
                "Best US-cash develop PF is still below 1 after costs. "
                "Suitability is event fit, not a promote. **promote=no.**"
            )
        else:
            lines.append(
                "Highest costed develop PF among US-cash tapes that clear n≥40. "
                "Holdout was not used to pick it. **promote=no** unless a later "
                "authorized screen says otherwise — this scan does not."
            )
        if top.get("spread_unmeasured"):
            lines.append("")
            lines.append(
                "Spread on this row is **assumed 60 pt (unmeasured)**. "
                "Prefer a Wine tape with measured spread if one ranks nearby."
            )
    lines += [
        "",
        "## Wrong-clock rows",
        "",
        "DAX / UKX / JP225 / AU200 / EU50 / FRA40 and other non-US opens can "
        "print a PF on this grammar because *some* bar falls in 09:45–11:30 ET. "
        "That is the wrong event. They stay research-only.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lock", type=Path, default=LOCK_PATH)
    args = ap.parse_args()
    lock = load_lock(args.lock)
    wine_rows, wine_man = collect_wine(lock)
    dukas_rows, dukas_man = collect_dukas(lock)
    rows = wine_rows + dukas_rows
    ranked = rank_scan_rows(rows, lock)
    candidates = trade_candidates(ranked)
    top = candidates[0] if candidates else None
    slim_rows = [slim_committed_report(r) for r in rows]
    slim_ranked = [slim_committed_report(r) for r in ranked]
    metrics = {
        "search_id": SEARCH_ID,
        "family_id": FAMILY_ID,
        "promote": False,
        "live_go": False,
        "holdout_start": lock["holdout_start"],
        "n_floor": lock["n_floor"],
        "n_rows": len(rows),
        "n_eligible": len(ranked),
        "n_trade_candidates": len(candidates),
        "rows": slim_rows,
    }
    ranking = {
        "search_id": SEARCH_ID,
        "score": lock["score"],
        "ranked": slim_ranked,
        "top_trade_candidate": slim_committed_report(top) if top else None,
        "note": (
            "Most suitable to trade requires us_cash_0930 AND develop n>=n_floor. "
            "A higher PF on GER40/UK100/JP225 is the wrong event."
        ),
        "promote": False,
        "live_go": False,
    }
    manifest = {
        "search_id": SEARCH_ID,
        "wine_m5": wine_man,
        "dukascopy_m5": dukas_man,
        "gaps": gaps(),
        "note": (
            "No invented candles. H1/M15 Wine leftovers listed as gaps. "
            "Dukascopy is public M5 bars (not ticks, not JForex)."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_slim_json(OUT_DIR / "metrics.json", metrics)
    write_slim_json(OUT_DIR / "ranking.json", ranking)
    (OUT_DIR / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_analysis(OUT_DIR / "ANALYSIS.md", lock, ranked, rows, top)
    print(json.dumps({"n_rows": len(rows), "n_eligible": len(ranked), "top": top["id"] if top else None}, indent=2))
    print(f"wrote {OUT_DIR}")


if __name__ == "__main__":
    main()
