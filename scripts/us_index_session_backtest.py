#!/usr/bin/env python3
"""Replay frozen ``ny_cash_orb_vwap_ema_flat`` on exported US-index M5.

Exit (frozen, not a search)
---------------------------
Signal is decided on the **close** of bar ``i`` (``scalp_signal_series``).
Fill is the **open** of bar ``i+1``. Flatten at the first later bar whose
open is at or after **15:45 ET** the same ET date. No SL/TP — those were
not in the indicator freeze. No overnight.

Costs (required; a zero-cost run is unfalsifiable)
--------------------------------------------------
Round-trip charged once at the fill bar, same shape as ``backtest.simulate``:

    (spread_pts + 2 * slippage_points) * point * contract * lots
    + 2 * commission_per_lot * lots

Defaults: slippage 10 points, commission 0 (spread-inclusive CFD assumption).
US100 live spread cap is 200 points — fills above that are skipped.

Holdout
-------
``HOLDOUT_START = 2026-06-01`` is locked here **before** any metric is used
for selection. This script does not search. Evaluate holdout; do not fit on it.

SAFETY: offline research only. promote / live_go = no.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from us_index_session_core import (  # noqa: E402
    FLAT_WARN,
    OR_MINUTES,
    scalp_signal_series,
    to_et,
    to_utc,
)

FAMILY_ID = "ny_cash_orb_vwap_ema_flat"
HOLDOUT_START = date(2026, 6, 1)
PROMOTE = False
LIVE_GO = False
DEFAULT_MAX_SPREAD = 200.0
DEFAULT_SLIPPAGE_POINTS = 10.0
DEFAULT_LOTS = 1.0


@dataclass(frozen=True)
class CostSpec:
    point_size: float = 0.01
    contract_size: float = 1.0
    lots: float = DEFAULT_LOTS
    commission_per_lot: float = 0.0
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
    et_date: str
    signal_time: str
    fill_time: str
    exit_time: str
    spread_pts: float
    cost: float
    pnl: float
    mae: float
    mfe: float


def _round_trip_cost(spread_pts: float, costs: CostSpec) -> float:
    return (
        (spread_pts + 2.0 * costs.slippage_points)
        * costs.point_size
        * costs.contract_size
        * costs.lots
        + 2.0 * costs.commission_per_lot * costs.lots
    )


def parse_meta(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "," not in line or line.startswith("key,"):
            continue
        k, v = line.split(",", 1)
        out[k.strip()] = v.strip()
    return out


def costs_from_meta(meta: dict[str, str], **overrides: float) -> CostSpec:
    point = float(meta.get("point") or 0.01)
    contract = float(meta.get("contract_size") or 1.0)
    kw = {
        "point_size": point if point > 0 else 0.01,
        "contract_size": contract if contract > 0 else 1.0,
    }
    kw.update(overrides)
    return CostSpec(**kw)


_KNOWN_HC_STEPS = (60, 300, 900, 1800, 3600, 14400, 86400)


def plausible_hc_step(delta: int, min_step: int = 60, max_step: int = 86400) -> bool:
    """True for an exact native MT5 cache step inside ``[min_step, max_step]``.

    M5 = 300, H1 = 3600, H4 = 14400, Daily = 86400. Weekend multiples are
    not used to locate the time table (4 × H1 must not match an H4 file).
    """
    d = int(delta)
    return d in _KNOWN_HC_STEPS and int(min_step) <= d <= int(max_step)


def read_mt5_hc(
    path: Path,
    *,
    min_step: int = 60,
    max_step: int = 86400,
    min_bars: int = 100,
) -> pd.DataFrame:
    """Read a Wine MT5 ``cache/{M5,H1,H4,Daily}.hc`` bar cache.

    Timestamps are broker server wall clocks stored as unix integers.
    Caller subtracts ``server_utc_offset_sec`` to get UTC.
    """
    data = Path(path).read_bytes()
    if len(data) < 512:
        raise ValueError(f"hc file too small: {path}")
    lo, hi = 1_600_000_000, 1_900_000_000
    start = -1
    for off in range(128, 720, 8):
        v0 = struct.unpack_from("<q", data, off)[0]
        v1 = struct.unpack_from("<q", data, off + 8)[0]
        if lo <= v0 <= hi and lo <= v1 <= hi and plausible_hc_step(v1 - v0, min_step, max_step):
            start = off
            break
    if start < 0:
        raise ValueError(f"no HTF time table in {path} (max_step={max_step})")
    times: list[int] = []
    off = start
    while off + 8 <= len(data):
        v = struct.unpack_from("<q", data, off)[0]
        if not (lo <= v <= hi):
            break
        if times and v < times[-1]:
            break
        times.append(v)
        off += 8
    n = len(times)
    if n < int(min_bars):
        raise ValueError(f"too few hc bars in {path}: {n}")

    def _prefixed_f8(pos: int) -> tuple[np.ndarray, int]:
        cnt = struct.unpack_from("<i", data, pos)[0]
        if cnt != n:
            raise ValueError(f"array count {cnt} != {n} at {pos}")
        pos += 4
        arr = np.frombuffer(data, dtype="<f8", count=n, offset=pos).copy()
        return arr, pos + n * 8

    def _prefixed_i32(pos: int) -> tuple[np.ndarray, int]:
        cnt = struct.unpack_from("<i", data, pos)[0]
        if cnt != n:
            raise ValueError(f"i32 count {cnt} != {n} at {pos}")
        pos += 4
        arr = np.frombuffer(data, dtype="<i4", count=n, offset=pos).copy()
        return arr, pos + n * 4

    def _prefixed_u8(pos: int) -> tuple[np.ndarray, int]:
        cnt = struct.unpack_from("<i", data, pos)[0]
        if cnt != n:
            raise ValueError(f"u64 count {cnt} != {n} at {pos}")
        pos += 4
        arr = np.frombuffer(data, dtype="<u8", count=n, offset=pos).copy()
        return arr, pos + n * 8

    open_, off = _prefixed_f8(off)
    high, off = _prefixed_f8(off)
    low, off = _prefixed_f8(off)
    close, off = _prefixed_f8(off)
    volume, off = _prefixed_u8(off)
    spread, off = _prefixed_i32(off)
    if not bool(np.all(high + 1e-9 >= low)):
        raise ValueError(f"OHLC invariant failed in {path}")
    return pd.DataFrame(
        {
            "server_epoch": np.asarray(times, dtype=np.int64),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": volume.astype(float),
            "spread": spread.astype(float),
        }
    )


def read_mt5_hc_m5(path: Path) -> pd.DataFrame:
    """Read M5 or H1 caches (step ≤ 3600). Use :func:`read_mt5_hc` for H4/Daily."""
    return read_mt5_hc(path, min_step=60, max_step=3600)


def infer_hc_tf(epochs: np.ndarray) -> str:
    if len(epochs) < 2:
        return "UNK"
    diffs = np.diff(np.asarray(epochs, dtype=np.int64))
    pos = diffs[diffs > 0]
    step = int(np.median(pos)) if len(pos) else 0
    return {
        60: "M1",
        300: "M5",
        900: "M15",
        1800: "M30",
        3600: "H1",
        14400: "H4",
        86400: "Daily",
    }.get(step, f"S{step}")


def hc_to_export_csv(
    hc_path: Path, csv_path: Path, symbol: str, tf: str | None = None
) -> Path:
    df = read_mt5_hc(hc_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    ts = pd.to_datetime(out["server_epoch"], unit="s", utc=True)
    label = tf or infer_hc_tf(out["server_epoch"].to_numpy())
    out.insert(0, "time", ts.dt.strftime("%Y.%m.%d %H:%M"))
    out.insert(1, "tf", label)
    out.insert(2, "symbol", symbol)
    out.to_csv(csv_path, index=False)
    return csv_path


def load_m5_csv(path: Path, server_utc_offset_sec: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "server_epoch" in df.columns:
        epoch = pd.to_numeric(df["server_epoch"], errors="coerce")
        server = pd.to_datetime(epoch, unit="s", utc=True)
    else:
        server = pd.to_datetime(df["time"], utc=True, errors="coerce")
    utc = server - pd.to_timedelta(int(server_utc_offset_sec), unit="s")
    df = df.copy()
    df["time_utc"] = utc
    df["time_server"] = server
    for col in ("open", "high", "low", "close", "tick_volume", "spread"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "tick_volume" not in df.columns:
        df["tick_volume"] = 1.0
    if "spread" not in df.columns:
        df["spread"] = 0.0
    df = df.dropna(subset=["open", "high", "low", "close", "time_utc"])
    df = df.sort_values("time_utc").reset_index(drop=True)
    return df


def _flatten_index(times: list[datetime], start: int) -> int | None:
    """First bar at or after 15:45 ET on the same ET date as ``times[start]``."""
    day = to_et(times[start]).date()
    for j in range(start, len(times)):
        et = to_et(times[j])
        if et.date() != day:
            return j - 1 if j > start else None
        if et.timetz().replace(tzinfo=None) >= FLAT_WARN:
            return j
    return len(times) - 1


def simulate_flatten(
    times: list[datetime],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    spread: np.ndarray,
    signals: np.ndarray,
    costs: CostSpec,
) -> list[Trade]:
    """Walk-forward fill / flatten. Signals must already be causal."""
    n = len(times)
    trades: list[Trade] = []
    i = 0
    while i < n - 1:
        sig = int(signals[i])
        if sig == 0:
            i += 1
            continue
        fill_i = i + 1
        if fill_i >= n:
            break
        if to_et(times[fill_i]).date() != to_et(times[i]).date():
            i += 1
            continue
        spr = float(spread[fill_i]) if np.isfinite(spread[fill_i]) else 0.0
        if costs.max_spread_points > 0 and spr > costs.max_spread_points:
            i += 1
            continue
        exit_i = _flatten_index(times, fill_i)
        if exit_i is None or exit_i <= fill_i:
            i += 1
            continue
        entry = float(open_[fill_i])
        exit_px = float(open_[exit_i])
        cost = _round_trip_cost(spr, costs)
        pnl = (exit_px - entry) * sig * costs.contract_size * costs.lots - cost
        window_h = high[fill_i:exit_i]
        window_l = low[fill_i:exit_i]
        if sig > 0:
            mae = float(entry - np.min(window_l)) if len(window_l) else 0.0
            mfe = float(np.max(window_h) - entry) if len(window_h) else 0.0
        else:
            mae = float(np.max(window_h) - entry) if len(window_h) else 0.0
            mfe = float(entry - np.min(window_l)) if len(window_l) else 0.0
        reason = "flatten_1545" if to_et(times[exit_i]).timetz().replace(
            tzinfo=None
        ) >= FLAT_WARN else "session_end"
        trades.append(
            Trade(
                side=sig,
                signal_i=i,
                fill_i=fill_i,
                exit_i=exit_i,
                entry=entry,
                exit=exit_px,
                reason=reason,
                et_date=str(to_et(times[i]).date()),
                signal_time=to_utc(times[i]).isoformat(),
                fill_time=to_utc(times[fill_i]).isoformat(),
                exit_time=to_utc(times[exit_i]).isoformat(),
                spread_pts=spr,
                cost=cost,
                pnl=pnl,
                mae=mae,
                mfe=mfe,
            )
        )
        i = exit_i + 1
    return trades


def metrics_from_trades(trades: list[Trade]) -> dict:
    pnls = [t.pnl for t in trades]
    if not pnls:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "net_pnl": 0.0,
            "avg_trade": 0.0,
            "profit_factor": 0.0,
            "max_dd": 0.0,
            "expectancy": 0.0,
            "longs": 0,
            "shorts": 0,
            "median_mae": 0.0,
            "median_mfe": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gw = float(sum(wins)) if wins else 0.0
    gl = float(-sum(losses)) if losses else 0.0
    if gl > 0:
        pf = gw / gl
    elif gw > 0:
        pf = float("inf")
    else:
        pf = 0.0
    eq = np.cumsum(np.asarray(pnls, dtype=float))
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    return {
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(pnls),
        "net_pnl": float(sum(pnls)),
        "avg_trade": float(np.mean(pnls)),
        "profit_factor": None if pf == float("inf") else float(pf),
        "max_dd": float(dd.min()) if len(dd) else 0.0,
        "expectancy": float(np.mean(pnls)),
        "longs": int(sum(1 for t in trades if t.side > 0)),
        "shorts": int(sum(1 for t in trades if t.side < 0)),
        "median_mae": float(np.median([t.mae for t in trades])),
        "median_mfe": float(np.median([t.mfe for t in trades])),
    }


def split_by_holdout(
    trades: list[Trade], holdout_start: date = HOLDOUT_START
) -> tuple[list[Trade], list[Trade]]:
    pre = [t for t in trades if date.fromisoformat(t.et_date) < holdout_start]
    post = [t for t in trades if date.fromisoformat(t.et_date) >= holdout_start]
    return pre, post


def run_file(
    csv_path: Path,
    meta_path: Path | None = None,
    *,
    costs: CostSpec | None = None,
    holdout_start: date = HOLDOUT_START,
) -> dict:
    meta: dict[str, str] = {}
    if meta_path and meta_path.is_file():
        meta = parse_meta(meta_path)
    offset = int(float(meta.get("server_utc_offset_sec") or 0))
    if costs is None:
        costs = costs_from_meta(meta)
    df = load_m5_csv(csv_path, offset)
    times = [to_utc(ts.to_pydatetime()) for ts in df["time_utc"]]
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    vol = df["tick_volume"].to_numpy(float)
    spread = df["spread"].to_numpy(float)
    signals = scalp_signal_series(times, high, low, close, vol)
    trades = simulate_flatten(times, open_, high, low, close, spread, signals, costs)
    pre, post = split_by_holdout(trades, holdout_start)
    symbol = str(meta.get("resolved") or meta.get("requested") or csv_path.stem)
    return {
        "family_id": FAMILY_ID,
        "promote": PROMOTE,
        "live_go": LIVE_GO,
        "symbol": symbol,
        "bars": int(len(df)),
        "from": str(df["time_utc"].iloc[0]) if len(df) else "",
        "to": str(df["time_utc"].iloc[-1]) if len(df) else "",
        "signals": int(np.count_nonzero(signals)),
        "holdout_start": str(holdout_start),
        "costs": asdict(costs),
        "or_minutes": OR_MINUTES,
        "exit": "flatten_1545_ET_next_bar_open_fill",
        "all": metrics_from_trades(trades),
        "pre_holdout": metrics_from_trades(pre),
        "holdout": metrics_from_trades(post),
        "note": (
            "Frozen combo replay. Holdout is evaluation-only. "
            "Not a develop screen. Not permission to --live."
        ),
        "trades": [asdict(t) for t in trades],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--hc", type=Path, default=None, help="MT5 cache/M5.hc")
    ap.add_argument("--symbol", default="US100")
    ap.add_argument("--server-utc-offset", type=int, default=10800)
    ap.add_argument("--meta", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--lots", type=float, default=DEFAULT_LOTS)
    ap.add_argument("--slippage-points", type=float, default=DEFAULT_SLIPPAGE_POINTS)
    ap.add_argument("--commission-per-lot", type=float, default=0.0)
    ap.add_argument("--max-spread-points", type=float, default=DEFAULT_MAX_SPREAD)
    args = ap.parse_args()
    if args.hc is not None:
        dump_dir = Path("results/us_index_data")
        dump_dir.mkdir(parents=True, exist_ok=True)
        args.csv = dump_dir / f"history_{args.symbol}_M5.csv"
        hc_to_export_csv(args.hc, args.csv, args.symbol)
        if args.meta is None:
            args.meta = dump_dir / f"symbol_meta_{args.symbol}.csv"
            args.meta.write_text(
                "key,value\n"
                f"requested,{args.symbol}\n"
                f"resolved,{args.symbol}\n"
                "digits,2\n"
                "point,0.01\n"
                "contract_size,1.0\n"
                f"server_utc_offset_sec,{args.server_utc_offset}\n"
                "tf,M5\n"
                f"source,{args.hc}\n"
            )
    if args.csv is None:
        ap.error("provide --csv or --hc")
    meta_path = args.meta
    if meta_path is None:
        guess = args.csv.parent / (
            "symbol_meta_" + args.csv.stem.replace("history_", "").replace("_M5", "") + ".csv"
        )
        if guess.is_file():
            meta_path = guess
    meta = parse_meta(meta_path) if meta_path and meta_path.is_file() else {}
    costs = costs_from_meta(
        meta,
        lots=args.lots,
        slippage_points=args.slippage_points,
        commission_per_lot=args.commission_per_lot,
        max_spread_points=args.max_spread_points,
    )
    report = run_file(args.csv, meta_path, costs=costs)
    slim = {k: v for k, v in report.items() if k != "trades"}
    text = json.dumps(slim, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
