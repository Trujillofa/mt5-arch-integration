#!/usr/bin/env python3
"""Fetch Dukascopy LIGHTCMDUSD ticks and resample to M5 (offline research).

Not Vantage USOUSD. Not CL=F. Spread is native tick ask-bid on this tape.
Writes results/oil_session_data/history_XTIUSD_M5.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import struct
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from oil_session_scalp_core import SERVER_MINUS_HOURS, et_from_server

BASE = "https://www.dukascopy.com/datafeed/LIGHTCMDUSD"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer": "https://www.dukascopy.com/swiss/english/marketwatch/historical/",
}
FMT = ">3I2f"
PRICE_DIV = 1000.0
POINT = 0.01


def _hours(start: datetime, end: datetime) -> list[datetime]:
    out = []
    t = start.replace(minute=0, second=0, microsecond=0)
    while t < end:
        out.append(t)
        t += timedelta(hours=1)
    return out


def _url(hour_utc: datetime) -> str:
    # month segment is 0-based
    return (
        f"{BASE}/{hour_utc.year}/{hour_utc.month-1:02d}/{hour_utc.day:02d}/"
        f"{hour_utc.hour:02d}h_ticks.bi5"
    )


def _fetch(hour_utc: datetime, cache: Path, session: requests.Session) -> Path | None:
    dest = cache / f"{hour_utc.strftime('%Y%m%d_%H')}.bi5"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = _url(hour_utc)
    try:
        r = session.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException:
        return None
    if r.status_code == 404 or not r.content:
        dest.write_bytes(b"")
        return None
    if r.status_code != 200:
        return None
    dest.write_bytes(r.content)
    return dest


def _decode(hour_utc: datetime, path: Path) -> pd.DataFrame:
    raw = path.read_bytes()
    if len(raw) < 20:
        return pd.DataFrame()
    try:
        blob = lzma.decompress(raw)
    except lzma.LZMAError:
        return pd.DataFrame()
    n = len(blob) // 20
    if n <= 0:
        return pd.DataFrame()
    recs = [struct.unpack(FMT, blob[i * 20 : (i + 1) * 20]) for i in range(n)]
    ms = np.fromiter((r[0] for r in recs), dtype=np.int64, count=n)
    ask = np.fromiter((r[1] for r in recs), dtype=np.float64, count=n) / PRICE_DIV
    bid = np.fromiter((r[2] for r in recs), dtype=np.float64, count=n) / PRICE_DIV
    t0 = hour_utc
    ts = [t0 + timedelta(milliseconds=int(m)) for m in ms]
    return pd.DataFrame({"ts": ts, "ask": ask, "bid": bid})


def resample_m5(ticks: pd.DataFrame) -> pd.DataFrame:
    if ticks.empty:
        return pd.DataFrame()
    ticks = ticks.sort_values("ts")
    ticks["ts"] = pd.to_datetime(ticks["ts"], utc=True)
    g = ticks.set_index("ts")
    ohlc = g["bid"].resample("5min", label="left", closed="left").ohlc()
    spr = ((g["ask"] - g["bid"]) / POINT).resample("5min", label="left", closed="left").median()
    vol = g["bid"].resample("5min", label="left", closed="left").count()
    out = ohlc.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close"})
    out["spread"] = spr.reindex(out.index)
    out["tick_volume"] = vol.reindex(out.index)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.reset_index().rename(columns={"ts": "utc"})


def to_export_csv(m5: pd.DataFrame) -> pd.DataFrame:
    utc = pd.to_datetime(m5["utc"], utc=True)
    et = utc.dt.tz_convert("America/New_York")
    server = et.dt.tz_localize(None) + pd.Timedelta(hours=SERVER_MINUS_HOURS)
    # verify clock inversion
    check = et_from_server(server)
    if not (check.dt.hour.to_numpy() == et.dt.hour.to_numpy()).all():
        bad = int((check.dt.hour.to_numpy() != et.dt.hour.to_numpy()).sum())
        raise SystemExit(f"clock inversion failed on {bad} bars")
    epoch = (server.dt.tz_localize("UTC").astype("int64") // 10**9).astype(np.int64)
    return pd.DataFrame(
        {
            "time": server.dt.strftime("%Y.%m.%d %H:%M"),
            "tf": "M5",
            "symbol": "XTIUSD",
            "open": m5["open"].to_numpy(float),
            "high": m5["high"].to_numpy(float),
            "low": m5["low"].to_numpy(float),
            "close": m5["close"].to_numpy(float),
            "tick_volume": m5["tick_volume"].fillna(1).astype(int),
            "spread": m5["spread"].fillna(0).to_numpy(float),
            "server_epoch": epoch,
        }
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2026-01-01")
    p.add_argument("--to", dest="end", default="2026-09-11")
    p.add_argument("--workers", type=int, default=12)
    args = p.parse_args(argv)
    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    cache = _ROOT / "results" / "oil_session_data" / "duka_ticks"
    cache.mkdir(parents=True, exist_ok=True)
    hours = _hours(start, end)
    print(f"hours={len(hours)} {start} → {end}", flush=True)
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=args.workers, pool_maxsize=args.workers)
    session.mount("https://", adapter)
    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_fetch, h, cache, session): h for h in hours}
        for i, fut in enumerate(as_completed(futs), 1):
            if fut.result() is not None:
                ok += 1
            if i % 250 == 0:
                print(f"  fetched {i}/{len(hours)} files_ok={ok}", flush=True)
    print(f"files_ok={ok}", flush=True)
    frames = []
    for h in hours:
        path = cache / f"{h.strftime('%Y%m%d_%H')}.bi5"
        if path.exists() and path.stat().st_size > 0:
            df = _decode(h, path)
            if not df.empty:
                frames.append(df)
    if not frames:
        raise SystemExit("no ticks decoded")
    ticks = pd.concat(frames, ignore_index=True)
    print(f"ticks={len(ticks)}", flush=True)
    m5 = resample_m5(ticks)
    print(f"m5={len(m5)}", flush=True)
    exp = to_export_csv(m5)
    out = _ROOT / "results" / "oil_session_data" / "history_XTIUSD_M5.csv"
    exp.to_csv(out, index=False)
    print("wrote", out, "sha256", hashlib.sha256(out.read_bytes()).hexdigest())
    print("spread p50", float(np.nanmedian(exp["spread"])), "p95", float(np.nanpercentile(exp["spread"], 95)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
