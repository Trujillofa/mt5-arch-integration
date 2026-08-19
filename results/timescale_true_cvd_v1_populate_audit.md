# Feed qualification audit — `timescale_true_cvd_v1`

| Field | Value |
|-------|--------|
| **When** | 2026-08-19 16:04 −05 |
| **Broker** | FP Markets (`fpmarkets`, `FPMarketsSC-Live`) |
| **Symbol** | **BTCUSD** (candidate only — **not locked**) |
| **Window** | last **36h** (clamped 24–48), resolved at click |
| **Tick count** | — |
| **last_trade_ratio** | — (no tape; not invented) |
| **volume_populated_ratio** | — (no tape; not invented) |
| **flag_direction_ratio** | — (no tape; not invented) |
| **Verdict** | **PENDING** |
| **promote / live_go** | **no / false** |
| **Instruments** | **TBD** |

## What was checked

Expected CSV is missing and empty `ticks/` is not a tape:

```
~/.mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/MQL5/Files/mt5_arch/ticks/
```

No `ticks_BTCUSD_fpmarkets.csv`, no `export_ticks.done`, no `ticks_*.csv` in other prefixes, Common/AppData, `results/tick_data/`, Downloads, or `/tmp`. `.tkc` was not read. `--audit` was not run on a fabricated file. No OHLCV screen. Timescale/Docker were not started.

`tick_cvd_core.py --audit` is ready; it has nothing to parse.

## Leftover (exact)

**Re-click Navigator is blocked because `terminal64.exe` is down — not a compile fail, not a wrong Files path.**

| Check | Result |
|-------|--------|
| Request still waiting | **Yes.** `export_ticks.request` still has `symbol=BTCUSD` / `hours=36` / `broker=fpmarkets` (mtime 15:44). A successful run deletes this file. |
| Script compiled | **Yes.** `ExportTicksCopyRange.ex5` present. MetaEditor: **0 errors**, 1 warning (`#property` 90). Compile 15:44:27. |
| Journal `TickExportCopyRangeNow` | **Absent.** UTF-16 journal `logs/20260819.log` last write **15:10:43** — `Terminal exit with code 0`. No script start, no CopyTicks error. |
| Files path | **Correct** (empty `ticks/` under the FP `MQL5/Files/mt5_arch` tree). |
| `terminal64` / Hyprland MT5 | **Not running.** Heartbeat frozen 15:10 (`symbol=US500`). FP + Vantage `wineserver` left alone. |

Do **not** restart Wine or launch `terminal64` from this session. After the user reopens the FP terminal themselves: Navigator → Scripts → **ExportTicksCopyRange**. Then copy the CSV to gitignored `results/tick_data/` and:

```bash
python3 scripts/tick_cvd_core.py --audit results/tick_data/ticks_BTCUSD_fpmarkets.csv
```

**Condition 2 (when a tape exists):** `last==0` on 100% of rows **or** BUY/SELL flags absent → **DISQUALIFY**. Do not fall back to `sign(close-open)*tick_volume`. Even **QUALIFY** does not lock BTCUSD. `promote=no`.
