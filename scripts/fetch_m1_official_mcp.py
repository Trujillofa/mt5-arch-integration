#!/usr/bin/env python3
"""Pull M1 bars from the official MT5 MCP server (route B) into an MT5-export CSV.

RESEARCH / OFFLINE data fetch. Read-only by construction: the client refuses
every tool except ``get_chart_history`` and ``get_time_information`` (the
official server also exposes trade_* tools; they are never reachable here).

    MT5_MCP_TOKEN=... python3 scripts/fetch_m1_official_mcp.py \
        --symbol XAUUSD --from 2024-01-01 --to 2026-09-25

Writes a tab-separated file in the terminal's own export layout
(<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <SPREAD>, broker server
time) plus ``<out>.meta.json`` (server UTC offset at fetch time, range, sha256).

Limits worth knowing:
- The server only serves bars inside the terminal's chart cache, which is
  capped by Tools > Options > Charts > "Max bars in chart" (Config/common.ini
  ``[Charts] MaxBars``). 100000 M1 bars is roughly three months. The script
  reports the first bar actually served so a silent truncation is visible.
- Only the terminal that bound 127.0.0.1:22346 first answers (see
  docs/HOWTO-MT5-AI-MCP.md); ``ss -ltnp | grep 22346`` shows which one.
- ``spread`` is the bar's MqlRates.spread, which equals the *minimum* tick
  spread inside the minute (checked against get_chart_ticks_history). The
  server omits the field on some bars (~0.3% of 2024-26 XAUUSD M1); those are
  written blank and counted in the meta file, never guessed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:22346/mcp"
ALLOWED_TOOLS = frozenset({"get_chart_history", "get_time_information"})
HEADER = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<SPREAD>"


class McpReadOnlyClient:
    def __init__(self, url: str, token: str, timeout: float = 120.0):
        host = urllib.parse.urlparse(url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"refusing non-loopback MCP url {url!r}: official MCP can trade")
        self.url, self._token, self.timeout = url, token, timeout
        self._session: str | None = None
        self._id = 0

    def _post(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            self._session = self._session or resp.headers.get("Mcp-Session-Id")
            return parse_rpc(resp.read().decode("utf-8", "replace"))

    def initialize(self) -> None:
        self._id += 1
        self._post({"jsonrpc": "2.0", "id": self._id, "method": "initialize",
                    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                               "clientInfo": {"name": "mt5-arch-m1-fetch", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, name: str, arguments: dict) -> dict:
        if name not in ALLOWED_TOOLS:
            raise PermissionError(f"tool {name!r} is not on the read-only allowlist")
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})
        if "error" in msg:
            raise RuntimeError(f"{name}: {msg['error']}")
        res = msg.get("result") or {}
        text = "".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            raise RuntimeError(f"{name}: {text[:300]}")
        return json.loads(text)


def parse_rpc(raw: str) -> dict:
    """The server answers either plain JSON or an SSE stream of data: lines."""
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    out: dict = {}
    for line in raw.splitlines():
        if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
            out = json.loads(line[5:])
    return out


def server_offset_hours(info: dict) -> float | None:
    """Server clock minus UTC, rounded to the half hour."""
    try:
        utc = datetime.fromisoformat(info["utc_time"].replace("Z", "+00:00"))
        srv = datetime.fromisoformat(info["trade_server_last_known_time"])
    except (KeyError, TypeError, ValueError):
        return None
    diff = (srv.replace(tzinfo=UTC) - utc).total_seconds() / 3600
    return round(diff * 2) / 2


def bar_line(b: dict) -> str:
    date, clock = b["time"].split(" ")
    return (f"{date}\t{clock}\t{b['open']}\t{b['high']}\t{b['low']}\t{b['close']}\t"
            f"{b['tick_volume']}\t{b.get('spread', '')}")


def fetch(client: McpReadOnlyClient, symbol: str, period: str, start: datetime,
          end: datetime, chunk_days: int, log=print) -> list[dict]:
    bars: dict[str, dict] = {}
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        res = client.call("get_chart_history", {
            "symbol": symbol, "period": period,
            "datetime_from": cur.strftime("%Y-%m-%dT%H:%M:%S"),
            "datetime_to": nxt.strftime("%Y-%m-%dT%H:%M:%S"), "limit": 100000})
        hist = res.get("history") or []
        for b in hist:
            bars[b["time"]] = b
        log(f"  {cur:%Y-%m-%d} -> {nxt:%Y-%m-%d}: {len(hist):>6} bars")
        cur = nxt
    return [bars[k] for k in sorted(bars)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--period", default="M1")
    ap.add_argument("--from", dest="start", required=True, help="server-time date, YYYY-MM-DD")
    ap.add_argument("--to", dest="end", required=True, help="exclusive, YYYY-MM-DD")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--chunk-days", type=int, default=14)
    ap.add_argument("--out", default="data/xauusd_m1_mcp.csv")
    a = ap.parse_args(argv)

    token = os.environ.get("MT5_MCP_TOKEN", "")
    if not token:
        sys.exit("MT5_MCP_TOKEN is not set (Tools > Options > MCP API key; "
                 "see docs/HOWTO-MT5-AI-MCP.md).")
    start, end = datetime.fromisoformat(a.start), datetime.fromisoformat(a.end)
    client = McpReadOnlyClient(a.url, token)
    client.initialize()
    info = client.call("get_time_information", {})
    offset = server_offset_hours(info)
    print(f"[mcp] {a.url}  server clock = UTC{offset:+g}h" if offset is not None
          else f"[mcp] {a.url}  server offset unknown")

    bars = fetch(client, a.symbol, a.period, start, end, a.chunk_days)
    if not bars:
        sys.exit("No bars served. Is the symbol in Market Watch, and is the range inside "
                 "the terminal's 'Max bars in chart' window?")
    first = datetime.strptime(bars[0]["time"], "%Y.%m.%d %H:%M:%S")
    if first - start > timedelta(days=4):
        print(f"WARNING: asked from {start:%Y-%m-%d} but the terminal served from "
              f"{first:%Y-%m-%d}. Raise Tools > Options > Charts > 'Max bars in chart' "
              "(common.ini [Charts] MaxBars) and restart that terminal to get more M1.")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join([HEADER, *map(bar_line, bars)]) + "\n"
    out.write_text(body, encoding="utf-8")
    meta = {
        "source": "official MT5 MCP get_chart_history",
        "url": a.url, "symbol": a.symbol, "period": a.period,
        "requested_from": a.start, "requested_to": a.end,
        "first_bar_server": bars[0]["time"], "last_bar_server": bars[-1]["time"],
        "rows": len(bars), "bars_missing_spread": sum("spread" not in b for b in bars),
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "server_utc_offset_h": offset,
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "spread_note": "MqlRates.spread = minimum tick spread within the bar",
    }
    Path(f"{out}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"{len(bars):,} bars {bars[0]['time']} -> {bars[-1]['time']} (server) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
