# Feed qualification audit — `timescale_true_cvd_v1`

| Field | Value |
|-------|--------|
| **When** | 2026-08-19 16:13 −05 |
| **Broker** | FP Markets (`fpmarkets`, `FPMarketsSC-Live`) |
| **Symbol** | **BTCUSD** (candidate only — **not locked**) |
| **Window** | last **36h** resolved at script OK (clamped 24–48). `from_msc=1787055155000` `to_msc=1787184755000`. Server `TimeCurrent` 2026-08-18 12:12:35 → 2026-08-20 00:12:35 (`server_utc_offset_sec=10804` ≈ +3h). UTC 2026-08-18 09:12:35 → 2026-08-19 21:12:35. |
| **Tick count** | **79382** |
| **last_trade_ratio** | **0.0** (`last_n=0`) |
| **volume_populated_ratio** | **0.0** (`volume_n=0`) |
| **flag_direction_ratio** | **0.0** (`flag_direction_n=0`) |
| **Verdict** | **DISQUALIFY** |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** |

## Terminal

`terminal64.exe /portable` was **already up** (pid 3448165, `WINEPREFIX=~/.mt5-fpmarkets`, cwd `FP Markets MT5 Terminal`). Journal: started **16:06:14**, authorized `84076984` on `FPMarketsSC-Live` through London 2. Bridge heartbeat fresh; `Mt5ArchBridge` on US500 H1. **Did not kill. Did not start a second process. Never `KILL_EXISTING=1`.**

## Dump (ran)

`Mt5ArchBridge` does **not** poll `export_ticks.request`. Request was refreshed (`symbol=BTCUSD` / `hours=36` / `broker=fpmarkets`). `ExportTicksCopyRange` was double-clicked in Navigator → Scripts on the existing session (dialog OK; Allow Algo Trading left checked; script never `OrderSend`).

Journal / Experts:

```
16:11:50  Scripts  script ExportTicksCopyRange (US30,M15) loaded successfully
16:12:32  ExportTicksCopyRange (US30,M15)  TickExportCopyRangeNow BTCUSD ticks=79382 from_msc=1787055155000 to_msc=1787184755000 had_request=yes NO ORDERS
16:12:32  ExportTicksCopyRange (US30,M15)  ExportTicksCopyRange finished ticks=79382
16:12:32  Scripts  script ExportTicksCopyRange (US30,M15) removed
```

`export_ticks.done`: `n=79382` `error=` empty. Request deleted. Host copy (gitignored): `results/tick_data/ticks_BTCUSD_fpmarkets.csv`. `.tkc` not read. Timescale/Docker not started. No OHLCV screen.

## Audit CLI

```bash
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_BTCUSD_fpmarkets.csv
```

```json
{
  "n_ticks": 79382,
  "last_n": 0,
  "volume_n": 0,
  "flag_direction_n": 0,
  "last_trade_ratio": 0.0,
  "volume_populated_ratio": 0.0,
  "flag_direction_ratio": 0.0,
  "verdict": "DISQUALIFY",
  "reason": "last==0 on all rows; true CVD impossible; no tick_volume fallback"
}
```

Condition 2: `last==0` on 100% of rows **and** BUY/SELL flags absent. Flags seen are quote-only (1030, 1158, 1028, 1026, 1154) — no bit 32/64. **No** `sign(close-open)*tick_volume` fallback.

BTCUSD is **not** locked. `promote=no` even if this had QUALIFY.

## Leftover

Tape exists and is **quote-only**. True CVD cannot be computed on this FP BTCUSD 36h dump. Pick another candidate later or stop. Do not screen OHLCV. Do not stand up Timescale.
