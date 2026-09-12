# OilSessionScalp — Design Memo (XTIUSD M5)

| Field | Value |
|-------|--------|
| **Date** | 2026-09-11 |
| **Status** | Overlay observe-only. Develop screen **SCREEN_FAIL** (0/96). **promote=no** |
| **Indicator** | `OilSessionScalp` v1.00 |
| **A-priori family** | `oil_london_orb_vwap_ema_flat` |
| **Repo boundary** | Visual + `iCustom` + logger — **no** `OrderSend` |
| **Primary chart** | XTIUSD / USOUSD / USOIL **M5** (WTI CFD) |
| **Logger** | `ForexSignalLogger` · `InpSignalBuffer=8` · `InpMaxSpreadPips=0` |
| **Lock** | `results/oil_session_scalp_lock.json` |
| **promote / live_go** | **no / false** |

> Not cash 09:30 `UsIndexSessionScalp`. Not closed `GoldSessionScalp` defined-R. Not BTC NY-desk as the ranked thesis. Do **not** edit `results/xau_loop_status.md`.

## 1. Why this exists

Gold, index, EURUSD, and BTC session overlays already exist. The next instrument is **WTI only**. Those lanes missed their costed goals; their **clock, causality, and engines** transfer — their frozen `family_id`s do not.

Oil has no US cash open. CME electronic 09:00 ET sits inside the NY energy box. EIA WTI inventories (Wednesday 10:30 ET) are the oil-native event analog of NFP.

## 2. What was read (harvest)

| Source | Kept | Rejected as default |
|--------|------|---------------------|
| `UsIndexSessionScalp` | Causal OR, VWAP×tick_volume, EMA 9/21, ATR%, Friday cutoff, buffer 8 | Cash 09:30 ORB |
| `GoldSessionScalp` (worktree) | London event clock, OR-width gate, NY desk ≠ cash | Closed 80% WR defined-R hunt |
| `BtcNySessionScalp` (worktree) | Lane file layout + lock protocol | BTC NY box as ranked family |
| EURUSD NY | DST ET clock, bid-space shorts, SL-first, null, edge-before-grid | `trend_continuation`; 6-lot heuristic |
| `ForexHtfPivotsFib` / `BtcTrendPullback` | ChartID objects, ATR offset, no `ObjectsDeleteAll` on `CHARTCHANGE` | H1/H4 swing as scalp trigger |
| `manual-trading-agent` `OIL` | WTI, point 0.01, Globex gap 21:00–22:00 UTC | Scanner alerts as an edge |
| `ctrader-trading-agent` `XTIUSD` | digits 2, point 0.01 prior, SessionClock, Friday EOD | FX H1 z-score walk-forward |
| crypto-agent | Promotion-gate language | No oil tape |

Transfers of index / gold / BTC / EURUSD families onto this tape are **scored, never ranked**.

## 3. Clock

`et = (server_naive - 7h).tz_localize('America/New_York', ambiguous='NaT', nonexistent='shift_forward')`. Never `load_m5_csv` constant `10800`.

| Box | Window | Role |
|-----|--------|------|
| London energy | first 30m after 08:00 Europe/London; entries after OR complete through 11:00 London | Primary event |
| NY energy | `[08:00, 11:30)` America/New_York | Second box (CME 09:00 is inside; not a 09:30 cash OR) |
| EIA blackout | Wed `[10:25, 10:40)` ET | Grid on/off |
| Friday cutoff | no new entries from 14:00 ET | Weekend gap |
| Globex gap | no entries `21:00–22:00` UTC | Maintenance |

Signals on the **close** of bar `i`. Fill at **open** of `i+1`. Forming bar never signals.

## 4. Frozen search (lock-before-peek)

96 configs: 3 families × SL `{1.0, 1.5}` ATR × TP `{1.0, 1.5}` R × time-stop `{6, 12}` × EIA blackout `{off, on}` × ATR% `{0.00015, 0.0003}`.

| Family | Thesis |
|--------|--------|
| `oil_london_orb_vwap_ema_flat` | London 30m OR + London-date VWAP + EMA 9/21 + ATR% + OR-width `[0.35, 2.5]` ATR |
| `oil_ny_inventory_drive` | NY energy 30m OR + 0.10 ATR buffer + VWAP + EMA; EIA blackout in grid |
| `oil_prior_day_reclaim` | Undercut/takeout of prior ET-day H/L then close-confirm reclaim inside London+NY overlap |

Holdout must not be `2026-01-01` (XAU), `2026-06-01` (index), or `2026-03-01` (BTC). Chosen after the tape is measured, before any PF.

## 5. Book / ranking

Eligible develop = `trades >= 40` and `net_pnl > 0`. Score = `PF * 1000 + expectancy`. 10-seed within-day return-rotation null. `SCREEN_FAIL` is a valid commit.

Costs: measured M5 spread; slip = 10% of median; skip fills above p95-ish cap; point/contract from the broker, not assumed 1000. Bid-space shorts. SL-first. One position. Flatten at box end.

## 6. Files

| Role | Path |
|------|------|
| Core | `scripts/oil_session_scalp_core.py` |
| Replay | `scripts/oil_session_scalp_backtest.py` |
| Screen | `scripts/oil_session_scalp_autoresearch.py` |
| Lock | `results/oil_session_scalp_lock.json` |
| Overlay | `mql5/Indicators/OilSessionScalp.mq5` |
| Clock | `mql5/Include/OilSessionUtils.mqh` |
| Runbook | `docs/HOWTO-OIL-SESSION-SCALP.md` |

## 7. Non-goals

No `--live`. No `OrderSend`. No retune of this 96-cell grid after holdout. No Brent as a ranked book. No `CL=F` as the costed tape. No 80% WR hunt. No US-index 1%/20% goal.


## 8. Screen result (2026-09-11)

**SCREEN_FAIL.** 0/96 develop-eligible (`trades>=40` and `net_pnl>0`) on the stamped Vantage `CL-OIL` M5 book. Signal-edge: London DEAD, NY EMPTY, reclaim DEAD vs 36.0 pt friction. Overlay default stays a-priori `oil_london_orb_vwap_ema_flat`.

| Family | develop n | WR | PF | Net | Eligible |
|--------|----------:|---:|---:|----:|:--------:|
| oil_london_orb_vwap_ema_flat | 146 | 36.3% | 0.64 | −7019 | no |
| oil_ny_inventory_drive | 0 | — | — | 0 | no |
| oil_prior_day_reclaim | 158 | 37.3% | 0.73 | −4139 | no |

Transfers (never ranked): index PF 0.77, gold 0.58, btc 0.48, eurusd_mr 0.45 — all develop-negative.

Book stamped: Vantage `CL-OIL` CopyRates M5 + spread via Mt5ArchBridge `dump_history.request` (100000 bars, 2025-04-15 → 2026-09-11). Clock admitted vs cTrader XTIUSD H1 (lag-0 0.946). Typical RT $36. Holdout `2026-04-01` unused for selection. Do not retune. Do not cut `min_trades`.
