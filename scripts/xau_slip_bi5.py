#!/usr/bin/env python3
"""Bounded XAU L1 slip audit: public Dukascopy .bi5 ticks, keep ticks.

Read-only live_book deals from the dirty Seven Desk checkout.
Does not rewrite xau_research_costs.json. No JForex / FreeServ / ismailfer.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import lzma
import random
import re
import struct
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
LIVE_BOOK = Path(
    "/home/yderf/Projects/trading/mt5-arch-integration/results/"
    "live_book_2026-08-15_2026-09-04"
)
OUT_DIR = _ROOT / "results" / "xau_slip_ticks"
SLIP_JSON = _ROOT / "results" / "xau_research_slip.json"
COSTS_JSON = _ROOT / "results" / "xau_research_costs.json"

CHUNK_SIZE = 20
STRUCT_FORMAT = ">3I2f"
BASE_URL = "https://www.dukascopy.com/datafeed"
SYMBOL = "XAUUSD"
# Dukascopy XAU integer prices / 1000 → 3 decimals (same as cTrader fetcher).
POINT_FACTOR = 1000.0
GOLD_POINT = 0.01  # MT5 gold point (research book)
CONTRACT = 100.0
# live_book EXPORT_MANIFEST / ANALYSIS: trade-server = UTC+3
SERVER_UTC_OFFSET_HOURS = 3
# reject merge_asof ticks older than this (not contemporaneous)
MAX_TICK_AGE_SEC = 2.0

WINDOW_START = datetime(2026, 8, 18, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 2, 23, 59, 59, tzinfo=UTC)

_HOUR_TICK_URL = re.compile(
    r"/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/(?P<hour>\d{2})h_ticks"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.dukascopy.com/swiss/english/marketwatch/historical/",
    "Accept": "*/*",
}


def dukascopy_tick_utc_from_raw_url(url: str, time_ms: int) -> datetime:
    """Hour-file URL month is zero-based; tick ms is offset from that UTC hour."""
    match = _HOUR_TICK_URL.search(url)
    if match is None:
        raise ValueError(f"not a Dukascopy hour-tick URL: {url}")
    hour_start = datetime(
        int(match["year"]),
        int(match["month"]) + 1,
        int(match["day"]),
        int(match["hour"]),
        tzinfo=UTC,
    )
    return hour_start + timedelta(milliseconds=int(time_ms))


def hour_url(symbol: str, hour_utc: datetime) -> str:
    y = hour_utc.year
    m0 = hour_utc.month - 1
    return (
        f"{BASE_URL}/{symbol}/{y}/{m0:02d}/{hour_utc.day:02d}/"
        f"{hour_utc.hour:02d}h_ticks.bi5"
    )


def unpack_bi5(payload: bytes, url: str, *, point: float = POINT_FACTOR) -> list[dict]:
    """Keep ticks: time (UTC), ask, bid, ask_vol, bid_vol."""
    data = lzma.decompress(payload)
    out: list[dict] = []
    for i in range(0, len(data), CHUNK_SIZE):
        chunk = data[i : i + CHUNK_SIZE]
        if len(chunk) < CHUNK_SIZE:
            break
        time_ms, ask_int, bid_int, ask_vol, bid_vol = struct.unpack(STRUCT_FORMAT, chunk)
        tick_time = dukascopy_tick_utc_from_raw_url(url, time_ms)
        out.append(
            {
                "time": tick_time,
                "ask": ask_int / point,
                "bid": bid_int / point,
                "ask_vol": float(ask_vol),
                "bid_vol": float(bid_vol),
            }
        )
    return out


def pack_bi5_records(rows: list[tuple[int, int, int, float, float]]) -> bytes:
    """Test helper: lzma-compress STRUCT_FORMAT records."""
    raw = b"".join(struct.pack(STRUCT_FORMAT, *r) for r in rows)
    return lzma.compress(raw)


@dataclass(frozen=True)
class HttpResp:
    status_code: int
    content: bytes


def fetch_url_smart(url: str, current_delay: float) -> tuple[HttpResp | None, float]:
    max_retries = 5
    attempt = 0
    req = urllib.request.Request(url, headers=HEADERS)
    while attempt < max_retries:
        try:
            time.sleep(current_delay)
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read()
                code = int(resp.status)
            if code == 200:
                if current_delay > 0.15:
                    current_delay = max(0.15, current_delay * 0.95)
                return HttpResp(code, body), current_delay
            if code == 404:
                return HttpResp(code, b""), current_delay
            if code in (403, 429):
                wait_time = (attempt + 1) * 5 + random.uniform(1, 3)
                print(f"rate-limit {code}; sleep {wait_time:.1f}s")
                time.sleep(wait_time)
                current_delay = min(5.0, current_delay * 2.0 + 0.5)
                attempt += 1
                continue
            print(f"server {code} retry")
            time.sleep(2)
            attempt += 1
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return HttpResp(404, b""), current_delay
            if exc.code in (403, 429):
                wait_time = (attempt + 1) * 5 + random.uniform(1, 3)
                print(f"rate-limit {exc.code}; sleep {wait_time:.1f}s")
                time.sleep(wait_time)
                current_delay = min(5.0, current_delay * 2.0 + 0.5)
                attempt += 1
                continue
            print(f"http {exc.code} retry")
            time.sleep(2)
            attempt += 1
        except urllib.error.URLError as exc:
            print(f"net {exc}; retry")
            time.sleep(max(2, attempt * 2))
            attempt += 1
        except TimeoutError as exc:
            print(f"timeout {exc}; retry")
            time.sleep(max(3, attempt * 3))
            current_delay = min(5.0, current_delay + 0.3)
            attempt += 1
    print(f"failed {url}")
    return None, current_delay


def hour_range(start: datetime, end: datetime) -> list[datetime]:
    cur = start.replace(minute=0, second=0, microsecond=0)
    last = end.replace(minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    while cur <= last:
        out.append(cur)
        cur += timedelta(hours=1)
    return out


def download_window(
    *,
    out_dir: Path,
    start: datetime = WINDOW_START,
    end: datetime = WINDOW_END,
    delay: float = 0.2,
) -> dict:
    out_dir = out_dir.resolve()
    bi5_dir = out_dir / "bi5"
    bi5_dir.mkdir(parents=True, exist_ok=True)
    hours = hour_range(start, end)
    n_ok = n_empty = n_fail = 0
    tick_n = 0
    daily: dict[date, list[dict]] = {}
    for hour in hours:
        url = hour_url(SYMBOL, hour)
        cache = bi5_dir / f"{hour:%Y%m%d_%H}.bi5"
        payload: bytes | None = None
        try:
            if cache.is_file() and cache.stat().st_size > 0:
                payload = cache.read_bytes()
            else:
                resp, delay = fetch_url_smart(url, delay)
                if resp is None:
                    n_fail += 1
                    continue
                if resp.status_code != 200 or not resp.content:
                    n_empty += 1
                    continue
                cache.write_bytes(resp.content)
                payload = resp.content
            rows = unpack_bi5(payload, url)
        except Exception as exc:
            print(f"hour fail {hour}: {exc}")
            n_fail += 1
            continue
        if not rows:
            n_empty += 1
            continue
        n_ok += 1
        tick_n += len(rows)
        daily.setdefault(hour.date(), []).extend(rows)
        if n_ok % 24 == 0:
            print(f"  hours_ok={n_ok} ticks={tick_n} last={hour.isoformat()}")

    ticks_path = out_dir / f"xauusd_ticks_{start.date()}_{end.date()}.csv.gz"
    all_rows: list[dict] = []
    for d in sorted(daily):
        all_rows.extend(sorted(daily[d], key=lambda r: r["time"]))
    if all_rows:
        with gzip.open(ticks_path, "wt", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["time", "ask", "bid", "ask_vol", "bid_vol"])
            w.writeheader()
            for r in all_rows:
                w.writerow(
                    {
                        "time": r["time"].isoformat(),
                        "ask": f"{r['ask']:.5f}",
                        "bid": f"{r['bid']:.5f}",
                        "ask_vol": f"{r['ask_vol']:.6g}",
                        "bid_vol": f"{r['bid_vol']:.6g}",
                    }
                )
    t0 = all_rows[0]["time"] if all_rows else None
    t1 = all_rows[-1]["time"] if all_rows else None
    manifest = {
        "symbol": SYMBOL,
        "source": "https://www.dukascopy.com/datafeed",
        "method": "public h_ticks.bi5; ticks kept (not aggregated to M1)",
        "window_utc": [start.isoformat(), end.isoformat()],
        "hours_requested": len(hours),
        "hours_ok": n_ok,
        "hours_empty": n_empty,
        "hours_fail": n_fail,
        "n_ticks": tick_n,
        "tick_min_utc": t0.isoformat() if t0 else None,
        "tick_max_utc": t1.isoformat() if t1 else None,
        "ticks_csv_gz": str(ticks_path.relative_to(_ROOT)) if all_rows else None,
        "point_factor": POINT_FACTOR,
        "format": "csv.gz columns=time,ask,bid,ask_vol,bid_vol (time=UTC ISO)",
    }
    (out_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("hours_ok", "hours_fail", "n_ticks")}, indent=2))
    return manifest


def _parse_server_time(raw: str) -> datetime:
    naive = datetime.strptime(raw.strip(), "%Y.%m.%d %H:%M:%S")
    # trade-server clock → UTC (EXPORT_MANIFEST server_utc_offset_hours=3)
    return (naive - timedelta(hours=SERVER_UTC_OFFSET_HOURS)).replace(tzinfo=UTC)


@dataclass(frozen=True)
class DealFill:
    broker: str
    symbol: str
    side: str  # buy | sell
    entry: str
    fill: float
    utc: datetime
    deal_id: int
    volume: float


def load_live_book_xau(book_dir: Path = LIVE_BOOK) -> list[DealFill]:
    out: list[DealFill] = []
    fp = json.loads((book_dir / "fp_deals_live.json").read_text())
    for d in fp["deals"]:
        if not str(d.get("symbol", "")).upper().startswith("XAU"):
            continue
        out.append(
            DealFill(
                broker="fpmarkets",
                symbol=str(d["symbol"]),
                side=str(d["type"]).lower(),
                entry=str(d.get("entry", "")),
                fill=float(d["price"]),
                utc=_parse_server_time(d["time"]),
                deal_id=int(d["deal_id"]),
                volume=float(d.get("volume") or 0),
            )
        )
    vt = json.loads((book_dir / "vantage_deals.json").read_text())
    for d in vt["deals"]:
        if not str(d.get("symbol", "")).upper().startswith("XAU"):
            continue
        out.append(
            DealFill(
                broker="vantage",
                symbol=str(d["symbol"]),
                side=str(d["action"]).lower(),
                entry=str(d.get("entry", "")),
                fill=float(d["price_open"]),
                utc=_parse_server_time(d["open_time"]),
                deal_id=int(d["deal_id"]),
                volume=float(d.get("volume") or 0),
            )
        )
    return out


def slip_points(side: str, fill: float, bid: float, ask: float) -> float:
    """Adverse-positive fill-vs-quote in gold points (0.01)."""
    if side == "buy":
        return (fill - ask) / GOLD_POINT
    if side == "sell":
        return (bid - fill) / GOLD_POINT
    raise ValueError(f"side {side}")


def merge_asof_slip(
    ticks: pd.DataFrame,
    deals: list[DealFill],
    *,
    max_age_sec: float = MAX_TICK_AGE_SEC,
) -> pd.DataFrame:
    if ticks.empty or not deals:
        return pd.DataFrame()
    t = ticks.sort_values("time").reset_index(drop=True)
    d = pd.DataFrame([asdict(x) for x in deals])
    d["utc"] = pd.to_datetime(d["utc"], utc=True)
    d = d.sort_values("utc").reset_index(drop=True)
    m = pd.merge_asof(
        d,
        t.rename(columns={"time": "tick_time"}),
        left_on="utc",
        right_on="tick_time",
        direction="backward",
    )
    m["tick_age_sec"] = (m["utc"] - m["tick_time"]).dt.total_seconds()
    m["usable"] = m["tick_time"].notna() & (m["tick_age_sec"] <= max_age_sec)
    slips = []
    for row in m.itertuples(index=False):
        if not bool(row.usable):
            slips.append(None)
            continue
        slips.append(slip_points(row.side, float(row.fill), float(row.bid), float(row.ask)))
    m["slip_points"] = slips
    return m


def _summarize(usable: pd.DataFrame) -> dict:
    if usable.empty:
        return {"n": 0, "median": None, "mean": None}
    s = usable["slip_points"].astype(float)
    return {
        "n": int(len(s)),
        "median": float(s.median()),
        "mean": float(s.mean()),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
        "min": float(s.min()),
        "max": float(s.max()),
        "usd_0_10_lot_median": float(s.median() * GOLD_POINT * CONTRACT * 0.10),
        "usd_1_00_lot_median": float(s.median() * GOLD_POINT * CONTRACT * 1.00),
    }


def audit(*, out_dir: Path, ticks_csv: Path | None = None) -> dict:
    if ticks_csv is None:
        cands = sorted(out_dir.glob("xauusd_ticks_*.csv.gz"))
        if not cands:
            raise SystemExit("no ticks csv.gz — run --download first")
        ticks_csv = cands[-1]
    ticks = pd.read_csv(ticks_csv)
    ticks["time"] = pd.to_datetime(ticks["time"], utc=True, format="ISO8601")
    deals = load_live_book_xau()
    merged = merge_asof_slip(ticks, deals)
    usable = merged[merged["usable"] & merged["slip_points"].notna()].copy()
    by_broker = {}
    for br, g in usable.groupby("broker"):
        by_broker[str(br)] = _summarize(g)
    payload = {
        "status": "MEASURED_FILL_VS_QUOTE" if len(usable) >= 5 else "GAP",
        "method": "dukascopy_bi5_merge_asof_backward",
        "label": "fill-vs-quote (Dukascopy L1), NOT request→fill",
        "promote": False,
        "do_not_overwrite_official_cost_book": True,
        "official_research_book": {
            "path": "results/xau_research_costs.json",
            "slippage_points": 0.0,
            "label": "UNMEASURED",
            "changed": False,
        },
        "window_utc": [WINDOW_START.isoformat(), WINDOW_END.isoformat()],
        "ticks_file": str(ticks_csv.relative_to(_ROOT)),
        "n_ticks": int(len(ticks)),
        "n_xau_deals": int(len(deals)),
        "n_usable": int(len(usable)),
        "max_tick_age_sec": MAX_TICK_AGE_SEC,
        "server_utc_offset_hours": SERVER_UTC_OFFSET_HOURS,
        "gold_point": GOLD_POINT,
        "measured_slippage_points": (
            float(usable["slip_points"].median()) if len(usable) >= 5 else None
        ),
        "usable_as_cost_assumption": False,
        "usable_as_cost_assumption_why": (
            "n RTs/deals is a two-week live_book sample, cross-venue "
            "(Dukascopy quote vs FP/Vantage fill). Too few to replace the "
            "official H1 slip-0 UNMEASURED book."
        ),
        "all_usable": _summarize(usable),
        "by_broker": by_broker,
        "n_rejected_stale_or_unmatched": int((~merged["usable"]).sum()) if len(merged) else 0,
    }
    return payload


def main() -> None:
    p = argparse.ArgumentParser(description="XAU L1 slip audit via public Dukascopy bi5")
    p.add_argument("--download", action="store_true")
    p.add_argument("--audit", action="store_true")
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--delay", type=float, default=0.2)
    p.add_argument("--ticks-csv", type=Path, default=None)
    args = p.parse_args()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.download:
        download_window(out_dir=args.out_dir, delay=args.delay)
    if args.audit:
        costs = json.loads(COSTS_JSON.read_text())
        if float(costs.get("slippage_points", 0)) != 0.0:
            raise SystemExit("refusing: official cost book slip is not 0")
        payload = audit(out_dir=args.out_dir, ticks_csv=args.ticks_csv)
        # merge into existing slip json without touching costs
        prev = json.loads(SLIP_JSON.read_text()) if SLIP_JSON.is_file() else {}
        prev["bi5_audit"] = payload
        prev["status"] = payload["status"]
        prev["measured_slippage_points"] = payload["measured_slippage_points"]
        prev["official_research_book"] = payload["official_research_book"]
        prev["do_not"] = (
            "Do not change xau_research_costs.json. Do not invent slip. "
            "fill-vs-quote is not request→fill. Do not promote."
        )
        SLIP_JSON.write_text(json.dumps(prev, indent=2) + "\n")
        print(json.dumps(payload, indent=2, default=str))
        if payload["n_usable"] < 5:
            print("GAP: n_usable < 5 — no cost-book number")
    if not args.download and not args.audit:
        raise SystemExit("pass --download and/or --audit")


if __name__ == "__main__":
    main()
