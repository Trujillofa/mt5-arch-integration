# US-index live week journal (observe + discretionary)

**Not a `family_id`.** `promote=no`. `live_go=false`. A green week is not a gate pass.

Frozen overlay: **UsIndexSessionScalp v1.41** on Vantage `DJ30.r` M5 — NY cash ORB + VWAP + EMA 9/21, signal buffer **8**, no `OrderSend`. Stops: overlay ATR **1.0 / 1.5** (not 1% of index price). Time-stop: 30–60 min discretionary + flatten by **15:45 ET**. Friday: overlay already blocks new signals from 14:00 ET.

Do **not** retune `InpFamily` or periods after looking at fills. Do **not** wire Vantage → Seven Desk. Do **not** attach Grid Scalper or `ForexHtfFibTester`. Do **not** pass `--live` to `live_trader.py`.

Vantage **DJ30.r M5** chart id `45942642771079` has the overlay. Attach `ForexSignalLogger` yourself (preset in `mql5/Presets/`). Preflight notes: `results/us_index_live_week_preflight.md`.

## Score process, not PF

For each fill mark yes/no:

| Field | Pass if |
| --- | --- |
| Window | Open in `[09:45, 11:30)` ET |
| Overlay combo | Close vs OR / VWAP / EMA9>21 matches the frozen family — else write **discretionary, not overlay** |
| SL | Present and ≥ broker `stops_level` (Vantage DJ30.r = 50 pt) |
| TP side | Buy: SL < entry < TP. Sell: TP < entry < SL |
| Stack | ≤ 2 clips. Vantage ~2 lots. Prop books via Seven Desk only, never Vantage→prop copy |
| Flatten | Flat by 15:45 ET. No overnight G10. No Friday runners |

If the fill is not the frozen combo, write “discretionary, not overlay” and **do not** change inputs.

## Rows

| Date | Book | Symbol | Side | Lots | Entry | SL | TP | Open ET | Close ET | Overlay? | SL ok | TP side | Stack | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | Vantage / Seven Desk |  |  |  |  |  |  |  |  |  |  |  |  |  |

## After the week

Compare `ForexSignalLogger` CSV vs fills. Count process misses (no SL, wrong-side TP, stack, outside window). Do not reopen v1–v8 screens. Do not invent a new `family_id`.
