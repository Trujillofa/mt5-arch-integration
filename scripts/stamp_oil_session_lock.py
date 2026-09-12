#!/usr/bin/env python3
"""Stamp oil lock data/costs AFTER M5 export and BEFORE any family PF."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from oil_session_scalp_core import et_from_server, load_oil_m5

LOCK_PATH = _ROOT / "results" / "oil_session_scalp_lock.json"


def _ctrader_h1() -> pd.DataFrame | None:
    p = Path("/home/yderf/Projects/trading/ctrader-trading-agent/candles.csv")
    if not p.is_file():
        return None
    df = pd.read_csv(p)
    xti = df[(df["symbol"] == "XTIUSD") & (df["timeframe"] == "H1")].copy()
    if xti.empty:
        return None
    xti["utc"] = pd.to_datetime(xti["candle_time"], utc=True)
    xti = xti.sort_values("utc")
    return xti


def _hourly_logret(close: pd.Series) -> pd.Series:
    return np.log(close.replace(0, np.nan)).diff()


def admit_clock(d_close_h1: pd.Series, ref_close_h1: pd.Series) -> dict:
    a = _hourly_logret(d_close_h1).dropna()
    b = _hourly_logret(ref_close_h1).dropna()
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(joined) < 50:
        return {"verdict": "too_short", "n": int(len(joined))}
    lags = {}
    for lag in range(-4, 5):
        lags[lag] = float(joined["a"].corr(joined["b"].shift(lag)))
    peak = max(lags, key=lambda k: abs(lags[k]))
    return {
        "n": int(len(joined)),
        "lag0_corr": lags[0],
        "peak_lag": int(peak),
        "lags": lags,
        "rejected_if_peak_not_0": peak != 0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--csv", type=Path, default=_ROOT / "results" / "oil_session_data" / "history_XTIUSD_M5.csv")
    p.add_argument("--lock", type=Path, default=LOCK_PATH)
    p.add_argument("--source", default="")
    p.add_argument("--broker", default="dukascopy")
    p.add_argument("--meta", type=Path, default=None)
    p.add_argument("--contract", type=float, default=100.0)
    p.add_argument("--point", type=float, default=0.01)
    p.add_argument("--digits", type=int, default=3)
    p.add_argument("--contract-note", default="")
    args = p.parse_args(argv)
    args.csv = args.csv.resolve()
    if args.meta is not None:
        args.meta = args.meta.resolve()
    raw = args.csv.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    df = pd.read_csv(args.csv)
    server = pd.to_datetime(pd.to_numeric(df["server_epoch"], errors="coerce"), unit="s")
    et = et_from_server(server)
    keep = et.notna()
    et = et.loc[keep]
    spread = pd.to_numeric(df.loc[keep, "spread"], errors="coerce").to_numpy(float)
    pos = spread[spread > 0]
    p50 = float(np.median(pos)) if len(pos) else 0.0
    p95 = float(np.percentile(pos, 95)) if len(pos) else 0.0
    p99 = float(np.percentile(pos, 99)) if len(pos) else 0.0
    zeros = int((spread <= 0).sum())
    slip = round(0.10 * p50, 4)
    cap = float(np.ceil(p95)) if p95 > 0 else 0.0
    d = load_oil_m5(args.csv, expected_sha256=sha)

    # H1 from M5 for admission
    utc = pd.DatetimeIndex(pd.to_datetime(d.times_utc)).tz_convert("UTC")
    close = pd.Series(d.close, index=utc)
    h1 = close.resample("1h").last().dropna()
    admission = {"verdict": "no_ctrader_ref"}
    ref = _ctrader_h1()
    if ref is not None:
        ref_s = ref.set_index("utc")["close"].astype(float)
        # align indexes to hour
        h1i = h1.copy()
        h1i.index = h1i.index.floor("h")
        ref_s.index = ref_s.index.floor("h")
        admission["m5_h1_vs_ctrader_xtiusd_h1"] = admit_clock(h1i, ref_s)
        # constant-10800 path: treat server_epoch as UTC and add 10800
        fake = pd.to_datetime(pd.to_numeric(df["server_epoch"], errors="coerce"), unit="s") + pd.Timedelta(seconds=10800)
        fake = fake.dt.tz_localize("UTC")
        fake_h1 = pd.Series(df["close"].to_numpy(float), index=fake).resample("1h").last().dropna()
        fake_h1.index = fake_h1.index.floor("h")
        admission["constant_10800_vs_ctrader"] = admit_clock(fake_h1, ref_s)
        a = admission["m5_h1_vs_ctrader_xtiusd_h1"]
        c = admission["constant_10800_vs_ctrader"]
        if a.get("peak_lag") == 0 and (c.get("lag0_corr") or 0) < (a.get("lag0_corr") or 0):
            admission["verdict"] = "clock admitted — unique lag-0 vs cTrader XTIUSD H1; constant-10800 worse"
        else:
            admission["verdict"] = "REVIEW — lag-0 not unique or 10800 not worse"

    lock = json.loads(args.lock.read_text())
    lock["data"].update(
        {
            "status": "stamped",
            "path": str(args.csv.relative_to(_ROOT)),
            "sha256": sha,
            "bars": int(len(d)),
            "time_min_server": str(df["time"].iloc[0]),
            "time_max_server": str(df["time"].iloc[-1]),
            "et_min": str(et.iloc[0]),
            "et_max": str(et.iloc[-1]),
            "et_dates": int(pd.Series(d.et_key).nunique()),
            "source": args.source
            or "Dukascopy LIGHTCMDUSD ticks resampled to M5 bid OHLC (not Vantage USOUSD CopyRates; not CL=F; not H1)",
            "broker": args.broker,
            "meta_path": str(args.meta.relative_to(_ROOT)) if args.meta else lock["data"].get("meta_path", ""),
            "clock_admission_status": admission["verdict"],
        }
    )
    lock["clock"]["admission"].update(admission)
    lock["book"]["contract_size"] = float(args.contract)
    lock["book"]["point_size"] = float(args.point)
    lock["book"]["digits"] = int(args.digits)
    lock["book"]["contract_note"] = args.contract_note or (
        "Dukascopy LIGHT.CMD/USD = 100 barrels / CFD. Overwrite from Vantage SymbolInfo when that M5 book is stamped."
    )
    lock["costs"].update(
        {
            "status": "stamped",
            "slippage_points": slip,
            "slippage_note": f"10% of measured M5 median spread {p50:.4f} pts",
            "max_spread_points": cap,
            "max_spread_note": f"ceil(p95={p95:.4f}) of measured M5 spread",
            "spread_measured": {"p50": p50, "p95": p95, "p99": p99, "zeros": zeros},
            "typical_rt_usd_at_median": (p50 + 2.0 * slip) * args.point * args.contract * 1.0,
        }
    )
    args.lock.write_text(json.dumps(lock, indent=2) + "\n")
    print("stamped", args.lock)
    print("bars", len(d), "et_dates", lock["data"]["et_dates"])
    print("spread", lock["costs"]["spread_measured"])
    print("admission", admission["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
