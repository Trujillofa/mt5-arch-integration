# Feed qualification audit — `timescale_true_cvd_v1`

| Field | Value |
|-------|--------|
| **When** | 2026-08-19 15:44 −05 |
| **Broker** | FP Markets (`fpmarkets`, `FPMarketsSC-Live`) |
| **Symbol** | **BTCUSD** (candidate only — **not locked**) |
| **Window** | last **36h** (clamped 24–48), resolved at click |
| **Tick count** | — |
| **last_trade_ratio** | — |
| **volume_populated_ratio** | — |
| **flag_direction_ratio** | — |
| **Verdict** | **PENDING** (dump did not run) |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** |

## What ran

Standalone script `ExportTicksCopyRange.mq5` + `TickCopyRangeExport.mqh` deployed into the FP prefix and compiled (`0` errors). Request file is in place:

```
symbol=BTCUSD
hours=36
broker=fpmarkets
```

`BTCUSD` is already in the live file-bridge `symbols.json` (with `EURUSD`, `GBPUSD`, `USDJPY`, `XAUUSD.r`). `US100` is not. One symbol only.

`CopyTicksRange` itself **did not execute**. No `terminal64.exe` process or Hyprland window was visible from this session. FP `wineserver` was left running. Bridge heartbeat was stale (~34 min). No CSV under `MQL5/Files/mt5_arch/ticks/`. `.tkc` / `ticks.dat` were not read. No OHLCV screen. Timescale/Docker were not started.

UsIndex M5 request polling lives inside `UsIndexSessionScalp` (a signal indicator). It was **not** reused or recompiled for ticks. Prefer the one-shot Script.

## Navigator recipe (required for the dump)

1. Do **not** restart Wine or `terminal64`. Do **not** set `KILL_EXISTING=1`.
2. On the **already-open** FP terminal: **Navigator → Scripts → ExportTicksCopyRange**.
3. Double-click (or drag onto any chart). The request file pins `BTCUSD` / 36h. A Script does not need Algo Trading.
4. Journal: `TickExportCopyRangeNow BTCUSD ticks=N … NO ORDERS`.
5. CSV: `MQL5/Files/mt5_arch/ticks/ticks_BTCUSD_fpmarkets.csv` and `export_ticks.done`.
6. Copy the CSV to gitignored `results/tick_data/`, then:

```bash
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_BTCUSD_fpmarkets.csv
```

If `last==0` on every row: **DISQUALIFY** that symbol for true CVD. Do not fall back to `tick_volume`. Even a QUALIFY does not lock the family onto BTCUSD this increment.

## Leftover

- Human click to run the Script, then populate ratios.
- Timescale still not up.
- No OHLCV screen under this `search_id`.
- `promote=no`.
