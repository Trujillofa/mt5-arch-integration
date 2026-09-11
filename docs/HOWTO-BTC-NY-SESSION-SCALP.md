# How to replay: BTC NY-desk overlap screen (offline)

**Role:** Offline research for BTCUSD M5 NY-desk overlap families. **`promote=no`. `live_go=false`.**
**Disposition:** `SCREEN_FAIL` (0/96). Overlay is observe-only.

Design freeze: [research/BTC-NY-SESSION-SCALP.md](research/BTC-NY-SESSION-SCALP.md).
Lock: `results/btc_ny_session_scalp_lock.json` (written before any signal).

## 1. Commands (`python3`, host numpy / pandas)

```bash
# Frozen transfers + a-priori family replay (needs locked CSV)
python3 scripts/btc_ny_session_scalp_backtest.py --mode all

# Develop screen (96 configs + 10-seed null). Do not rewrite the lock.
python3 scripts/btc_ny_session_scalp_autoresearch.py
```

CSV (gitignored): `results/btc_ny_data/history_BTCUSD_M5.csv` from FP `BTCUSD/cache/M5.hc` via `read_mt5_hc`. Do **not** run `export-instruments-from-wine-mt5.sh` (it kills `terminal64`).

## 2. Clock

`et = (server - 7h).localize(America/New_York)`. Entry `[08:00, 11:30)` ET. Flatten 11:30. Friday ≥14:00 no new entries.

## 3. Overlay

`BtcNySessionScalp` signal **buffer 8**. Logger preset `mql5/Presets/ForexSignalLogger-BtcNySessionScalp.set`. Compile MetaEditor F7. Do not run full `18-install` (overwrites live `Mt5ArchBridge`). Leave `BtcTrendPullback` buffer 7 on H1 charts.

## 4. Explicitly not next

- Retune the 96-cell grid on this tape
- Promote on index-transfer PF 1.08 (15:45 hold, not a scalp)
- Reopen closed theses in the lock
- Edit `results/xau_loop_status.md`
- `--live` / `OrderSend`
