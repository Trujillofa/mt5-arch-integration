# Feed qualification audit — `timescale_true_cvd_v1`

All three FP CopyTicks candidates ran. **None QUALIFY.** Instruments stay **TBD**. `promote=no`.

| Symbol | Ticks | last_trade_ratio | volume_populated_ratio | flag_direction_ratio | Verdict |
|--------|------:|-----------------:|-----------------------:|---------------------:|---------|
| BTCUSD | 79382 | 0.0 | 0.0 | 0.0 | **DISQUALIFY** |
| US100 | 539079 | 0.0 | 0.0 | 0.0 | **DISQUALIFY** |
| XAUUSD.r | 489634 | 0.0 | 0.0 | 0.0 | **DISQUALIFY** |

`last==0` on 100% of rows on every tape. BUY/SELL flags absent (quote-only bits only). **No** `sign(close-open)*tick_volume` fallback. QUALIFY would still not lock an instrument.

| Field | Value |
|-------|--------|
| **When** | 2026-08-19 17:02 −05 |
| **Broker** | FP Markets (`fpmarkets`, `FPMarketsSC-Live`) |
| **Window** | last **36h** at each script OK (clamped 24–48). `server_utc_offset_sec=10804` ≈ +3h |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** |

## Terminal

`terminal64.exe /portable` was **already up** (pid 3448165, `WINEPREFIX=~/.mt5-fpmarkets`). Journal start **16:06:14**, authorized `84076984` on `FPMarketsSC-Live`. **Did not kill. Did not start a second process. Never `KILL_EXISTING=1`.** Live names: **US100** (not USTEC/NAS100), **XAUUSD.r** (bare `XAUUSD` candles empty). Both had open chart tabs.

## Dumps (ran)

`Mt5ArchBridge` does **not** poll `export_ticks.request`. Each dump: refresh request (`hours=36` / `broker=fpmarkets`) then Navigator → Scripts → `ExportTicksCopyRange` on the existing session. Script never `OrderSend`. `.tkc` not read. Timescale/Docker not started. No OHLCV screen. No OKX.

Journal / Experts:

```
16:11:50  Scripts  script ExportTicksCopyRange (US30,M15) loaded successfully
16:12:32  ExportTicksCopyRange (US30,M15)  TickExportCopyRangeNow BTCUSD ticks=79382 from_msc=1787055155000 to_msc=1787184755000 had_request=yes NO ORDERS
16:54:00  Scripts  script ExportTicksCopyRange (BTCUSD,M15) loaded successfully
16:54:07  ExportTicksCopyRange (BTCUSD,M15)  TickExportCopyRangeNow US100 ticks=539079 from_msc=1787057647000 to_msc=1787187247000 had_request=yes NO ORDERS
17:01:56  Scripts  script ExportTicksCopyRange (BTCUSD,M15) loaded successfully
17:01:58  ExportTicksCopyRange (BTCUSD,M15)  TickExportCopyRangeNow XAUUSD.r ticks=489634 from_msc=1787058120000 to_msc=1787187720000 had_request=yes NO ORDERS
```

Host copies (gitignored): `results/tick_data/ticks_{BTCUSD,US100,XAUUSD.r}_fpmarkets.csv`.

## Audit CLI

```bash
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_BTCUSD_fpmarkets.csv
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_US100_fpmarkets.csv
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_XAUUSD.r_fpmarkets.csv
```

All three: `verdict=DISQUALIFY`, `reason=last==0 on all rows; true CVD impossible; no tick_volume fallback`.

Flags seen are quote-only (1030, 1158, 1028, 1026, 1154) — no bit 32/64.

## Path 2 leftover

FP Markets CopyTicks on BTCUSD / US100 / XAUUSD.r is **quote-only**. Path 2 has **no FP last-trade tape**. Do not lock a symbol. Do not screen OHLCV. Do not stand up Timescale. Do not import OKX into this repo.
