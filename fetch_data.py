#!/usr/bin/env python3
"""
Fetch XAUUSD M15 + H1 OHLC (~12–24 months) into xauusd_data.csv.

Priority:
1. Official MetaTrader5 package (Windows) via copy_rates_range
2. Wine MT5 export CSV produced by Scripts/ExportXauHistory.mq5
3. mt5linux RPyC bridge (often IPC-timeout under Wine 11)
4. Linux offline bridge (Dukascopy H1 + yfinance)

Re-export from Wine (recommended when terminal is authenticated):
  compile ExportXauHistory.mq5 and run via export_xau.ini StartUp
  (see scripts/export-xau-from-wine-mt5.sh)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT_CSV = Path(__file__).resolve().parent / "xauusd_data.csv"
SYMBOL = "XAUUSD"
MONTHS = 24

WINEPREFIX = Path(os.environ.get("WINEPREFIX", Path.home() / ".mt5-vantage"))
WINE_MT5_EXPORT = (
    WINEPREFIX
    / "drive_c/Program Files/Vantage International MT5/MQL5/Files/xauusd_mt5_export.csv"
)
DUKAS_H1 = Path(
    "/home/yderf/Projects/trading/ctrader-trading-agent/data/dukascopy/"
    "xauusd_h1_2022-01-01_2026-03-01.csv"
)


def _try_import_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5
    except ImportError:
        return None


def fetch_via_mt5(mt5) -> pd.DataFrame:
    if not mt5.initialize():
        raise RuntimeError(f"mt5.initialize failed: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"symbol_select failed: {mt5.last_error()}")
        utc_to = datetime.now(timezone.utc)
        utc_from = utc_to - timedelta(days=int(MONTHS * 30.5))
        frames = []
        for tf_name, tf_const in (("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1)):
            rates = mt5.copy_rates_range(SYMBOL, tf_const, utc_from, utc_to)
            if rates is None or len(rates) == 0:
                raise RuntimeError(f"copy_rates_range empty {tf_name}: {mt5.last_error()}")
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df["timeframe"] = tf_name
            df["symbol"] = SYMBOL
            frames.append(
                df[["time", "timeframe", "symbol", "open", "high", "low", "close", "tick_volume"]]
            )
            print(f"MT5 {tf_name}: {len(df)} bars {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
        return pd.concat(frames, ignore_index=True)
    finally:
        mt5.shutdown()


def fetch_via_wine_export(path: Path = WINE_MT5_EXPORT) -> pd.DataFrame:
    """Load CSV written by ExportXauHistory.mq5 under Wine Vantage terminal."""
    if not path.is_file():
        raise FileNotFoundError(f"Wine export missing: {path}")
    df = pd.read_csv(path)
    # MT5 TimeToString → "2024.08.16 18:15"
    df["time"] = pd.to_datetime(df["time"], format="%Y.%m.%d %H:%M", utc=True)
    df["symbol"] = df.get("symbol", SYMBOL)
    need = ["time", "timeframe", "symbol", "open", "high", "low", "close", "tick_volume"]
    for c in need:
        if c not in df.columns:
            raise RuntimeError(f"export missing column {c}")
    df = df[need].copy()
    age_h = (datetime.now(timezone.utc) - df["time"].max().to_pydatetime().replace(tzinfo=timezone.utc)).total_seconds() / 3600
    print(
        f"Wine MT5 export: {path} size={path.stat().st_size} "
        f"age_hours={age_h:.1f}"
    )
    for tf in ("M15", "H1"):
        sub = df[df["timeframe"] == tf]
        if sub.empty:
            raise RuntimeError(f"export has no {tf} rows")
        print(f"  {tf}: n={len(sub)} {sub['time'].min()} → {sub['time'].max()}")
    return df


def fetch_via_mt5linux() -> pd.DataFrame:
    """RPyC bridge — often hangs with IPC timeout under Wine 11."""
    from mt5linux import MetaTrader5  # type: ignore

    host = os.environ.get("MT5_RPYC_HOST", "127.0.0.1")
    port = int(os.environ.get("MT5_RPYC_PORT", "18812"))
    path = os.environ.get(
        "MT5_TERMINAL_PATH",
        r"C:\Program Files\Vantage International MT5\terminal64.exe",
    )
    mt5 = MetaTrader5(host=host, port=port)
    if not mt5.initialize(path=path):
        if not mt5.initialize():
            raise RuntimeError(f"mt5linux initialize failed: {mt5.last_error()}")
    try:
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"symbol_select: {mt5.last_error()}")
        utc_to = datetime.now(timezone.utc)
        utc_from = utc_to - timedelta(days=int(MONTHS * 30.5))
        frames = []
        for tf_name, tf_const in (("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1)):
            rates = mt5.copy_rates_range(SYMBOL, tf_const, utc_from, utc_to)
            if rates is None or len(rates) == 0:
                raise RuntimeError(f"empty rates {tf_name}")
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df["timeframe"] = tf_name
            df["symbol"] = SYMBOL
            frames.append(
                df[["time", "timeframe", "symbol", "open", "high", "low", "close", "tick_volume"]]
            )
            print(f"mt5linux {tf_name}: {len(df)} bars")
        return pd.concat(frames, ignore_index=True)
    finally:
        mt5.shutdown()


def _h1_from_dukascopy() -> pd.DataFrame:
    if not DUKAS_H1.is_file():
        raise FileNotFoundError(str(DUKAS_H1))
    raw = pd.read_csv(DUKAS_H1)
    raw["time"] = pd.to_datetime(raw["timestamp"], unit="ms", utc=True)
    df = raw[raw["high"] > raw["low"]].copy()
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(MONTHS * 30.5))
    df = df[df["time"] >= cutoff].copy()
    df["timeframe"] = "H1"
    df["symbol"] = SYMBOL
    df["tick_volume"] = 0
    return df[["time", "timeframe", "symbol", "open", "high", "low", "close", "tick_volume"]]


def _synthesize_m15_from_h1(h1: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(42)
    for _, r in h1.iterrows():
        t0 = r["time"]
        o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        path = np.linspace(o, c, 5)
        for i in range(4):
            po, pc = path[i], path[i + 1]
            noise = abs(h - l) * 0.05 * rng.random()
            hi = min(h, max(po, pc) + noise)
            lo = max(l, min(po, pc) - noise)
            if hi < lo:
                hi, lo = lo, hi
            rows.append(
                {
                    "time": t0 + pd.Timedelta(minutes=15 * i),
                    "timeframe": "M15",
                    "symbol": SYMBOL,
                    "open": po,
                    "high": hi,
                    "low": lo,
                    "close": pc,
                    "tick_volume": 0,
                }
            )
    return pd.DataFrame(rows)


def fetch_via_offline_bridge() -> pd.DataFrame:
    print("Using offline bridge (Dukascopy/yfinance) — prefer Wine export when possible")
    h1 = _h1_from_dukascopy()
    print(f"Dukascopy H1: {len(h1)}")
    try:
        import yfinance as yf

        t = yf.Ticker("GC=F")
        yh = t.history(period="2y", interval="1h", auto_adjust=True)
        if not yh.empty:
            out = yh.reset_index()
            out = out.rename(
                columns={
                    out.columns[0]: "time",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "tick_volume",
                }
            )
            out["time"] = pd.to_datetime(out["time"], utc=True)
            out["timeframe"] = "H1"
            out["symbol"] = SYMBOL
            out["tick_volume"] = out.get("tick_volume", 0)
            tail = out[out["time"] > h1["time"].max()]
            if len(tail):
                h1 = pd.concat([h1, tail[h1.columns]], ignore_index=True)
                print(f"Appended {len(tail)} yfinance H1 bars")
    except Exception as e:
        print(f"yfinance optional append failed: {e}")
    m15 = _synthesize_m15_from_h1(h1)
    return pd.concat([m15, h1], ignore_index=True)


def main() -> int:
    prefer = os.environ.get("MT5_FETCH_BACKEND", "auto")  # auto|wine|mt5|mt5linux|offline
    df = None
    source = ""

    # 1) Wine MT5 script export (real broker OHLC under Wine)
    if prefer in ("auto", "wine") and WINE_MT5_EXPORT.is_file():
        try:
            df = fetch_via_wine_export()
            source = f"wine_export:{WINE_MT5_EXPORT}"
        except Exception as e:
            print(f"Wine export path failed: {e}")

    # 2) Official package
    if df is None and prefer in ("auto", "mt5"):
        mt5 = _try_import_mt5()
        if mt5 is not None:
            try:
                df = fetch_via_mt5(mt5)
                source = "MetaTrader5.copy_rates_range"
            except Exception as e:
                print(f"MetaTrader5 package path failed: {e}")

    # 3) mt5linux RPyC (optional; may hang)
    if df is None and prefer in ("mt5linux",) or (
        df is None and prefer == "auto" and os.environ.get("MT5_TRY_RPYC") == "1"
    ):
        try:
            print("Trying mt5linux RPyC (may timeout under Wine)...")
            df = fetch_via_mt5linux()
            source = "mt5linux.rpyc"
        except Exception as e:
            print(f"mt5linux failed: {e}")

    # 4) Offline
    if df is None:
        df = fetch_via_offline_bridge()
        source = "offline_bridge"

    df = df.sort_values(["timeframe", "time"]).drop_duplicates(
        subset=["timeframe", "time"]
    ).reset_index(drop=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    for tf in ("M15", "H1"):
        sub = df[df["timeframe"] == tf]
        span = (sub["time"].max() - sub["time"].min()).days if len(sub) else 0
        print(f"Saved {tf}: n={len(sub)} span_days={span}")

    print(f"Wrote {OUT_CSV} ({OUT_CSV.stat().st_size} bytes) source={source}")
    h1 = df[df["timeframe"] == "H1"]
    if h1.empty or (h1["time"].max() - h1["time"].min()).days < 300:
        print("ERROR: H1 coverage < ~12 months", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
