# How to replay: oil session scalp screen (offline)

**Role:** Offline research for XTIUSD / CL-OIL M5 London+NY energy families. **`promote=no`. `live_go=false`.**
**Disposition:** `SCREEN_FAIL` on stamped Vantage `CL-OIL` M5 (holdout `2026-04-01` unused for selection). Overlay is observe-only.

Design freeze: [research/OIL-SESSION-SCALP.md](research/OIL-SESSION-SCALP.md).
Lock: `results/oil_session_scalp_lock.json` (families/clock/grid frozen before any oil PF).

## 1. Commands (`python3`, host numpy / pandas)

```bash
# Live-safe M5 dump (does not kill terminal64): drop the request after the overlay is on a chart
#   MQL5/Files/mt5_arch/export_oil.request
# or run Scripts/ExportOilM5.mq5. Do NOT run ExportInstrumentHistory.mq5 on a live prefix.

python3 scripts/signal_edge_diagnostic.py --lane oil
python3 scripts/oil_session_scalp_backtest.py --mode all
python3 scripts/oil_session_scalp_autoresearch.py
```

CSV (gitignored): `results/oil_session_data/history_CL-OIL_M5.csv` from Vantage Mt5ArchBridge `dump_history.request`. Do **not** lock `M15.hc`, cTrader H1, or `CL=F`.

## 2. Clock

`et = (server - 7h).localize(America/New_York)`. London energy: OR 08:00–08:30 London, entries through 11:00 London. NY energy: `[08:00, 11:30)` ET. EIA Wed `[10:25, 10:40)` ET. Globex gap 21:00–22:00 UTC. Friday ≥14:00 ET no new entries.

## 3. Overlay

`OilSessionScalp` signal **buffer 8**. Logger preset `mql5/Presets/ForexSignalLogger-OilSessionScalp.set`. Compile MetaEditor F7. Do not run full `18-install` on a live `Mt5ArchBridge` unless you intend to overwrite it.

## 4. Explicitly not next

- Retune the 96-cell grid after holdout
- Promote a transfer PF
- Reopen closed theses in the lock
- Edit `results/xau_loop_status.md`
- `--live` / `OrderSend`

## Bridge dump (preferred)

Live Vantage Mt5ArchBridge (EURUSD writer) polls `MQL5/Files/mt5_arch/dump_history.request`.

Three ANSI lines: symbol, timeframes, months. Example: `CL-OIL` / `M5` / `60`.

Writes `history_CL-OIL_M5.csv` and `symbol_meta_CL-OIL.csv`. No `OrderSend`. Do not run `ExportInstrumentHistory.mq5`.

After a new `Mt5ArchBridge.ex5` compile, reattach the EA on the writer chart with `InpBroker=vantage` so the running build sees the request gate.
