# BtcNySessionScalp — Design Memo (BTCUSD M5)

| Field | Value |
|-------|--------|
| **Date** | 2026-09-11 |
| **Status** | Overlay shipped; develop screen **SCREEN_FAIL** (0/96 eligible); **promote=no** |
| **Indicator** | `BtcNySessionScalp` v1.00 |
| **A-priori family** | `btc_ny_overlap_vwap_ema_flat` |
| **Repo boundary** | Visual + `iCustom` + logger — **no** `OrderSend` |
| **Primary chart** | BTCUSD **M5** |
| **Logger** | `ForexSignalLogger` · `InpSignalBuffer=8` · `InpMaxSpreadPips=0` |
| **Lock** | `results/btc_ny_session_scalp_lock.json` |
| **promote / live_go** | **no / false** |

> Not `BtcTrendPullback` (H1/H4, buffer 7). Not `UsIndexSessionScalp` cash 09:30. Not `GoldSessionScalp` London OR. Do **not** edit `results/xau_loop_status.md`.

## 1. Why this exists

Gold and index session overlays exist. The next instrument is BTC. Prior work already killed cash-open ORB on BTC H1 (`ny-1330`) and FX-style session gates as a BTC liquidity model. This lane freezes a **NY-desk overlap** box — `[08:00, 11:30)` America/New_York — and searches three new families on a costed FP M5 book.

## 2. Clock

`et = (server_naive - 7h).tz_localize('America/New_York', ambiguous='NaT')`. Never `load_m5_csv` constant `10800`. Admission: unique lag-0 vs Binance H1 (long book corr 0.960; M5 vs 2026 spot 0.917; constant-10800 rejected at 0.53).

## 3. Frozen search (lock-before-peek)

96 configs: 3 families × SL {1.0, 1.5} ATR × TP {1.0, 1.5} R × time-stop {6, 12} × NFP blackout {off, on} × ATR% {0.00015, 0.0003}.

| Family | Thesis |
|--------|--------|
| `btc_ny_overlap_vwap_ema_flat` | NY-desk VWAP + EMA 9/21 + ATR% |
| `btc_ny_overlap_atr_drive` | First 30m NY-desk range + 0.10 ATR buffer + VWAP + EMA |
| `btc_ny_overlap_htf_pullback` | Completed H1 EMA50/200 **bias** + M5 reclaim vs chart EMA-slow (default 21 — mirrors `htf_pullback_signals()` in the core) inside the box |

Transfers (never ranked): unmodified index 09:30 ORB (flatten 15:45) and gold London 30m OR + NY metals on this BTC tape.

## 4. Book

FP BTCUSD M5.hc, 100006 bars, 2025-04-21 → 2026-08-20. Point 0.01, contract 1, lots 1, slip **160** (stated; 10% of median 1600-pt spread), cap 2000. Holdout `et_date >= 2026-03-01` (not XAU 2026-01-01, not index 2026-06-01). Typical RT at median spread ≈ **$19.20**.

## 5. Screen result

**SCREEN_FAIL.** 0/96 develop-eligible (`trades>=40` and `net_pnl>0`). Best-of-family develop:

| Family | n | WR | PF | Net |
|--------|--:|---:|---:|----:|
| vwap_ema | 217 | 37.8% | 0.70 | −$6,057 |
| atr_drive | 0 | — | — | $0 |
| htf_pullback | 188 | 43.1% | 0.75 | −$5,674 |

Index transfer develop PF 1.08 is the **15:45 drift ride**, not a scalp (holdout PF 0.88). Gold transfer develop PF 0.72. Overlay default stays the a-priori VWAP+EMA family.

## 6. Files

| Role | Path |
|------|------|
| Core | `scripts/btc_ny_session_scalp_core.py` |
| Replay | `scripts/btc_ny_session_scalp_backtest.py` |
| Screen | `scripts/btc_ny_session_scalp_autoresearch.py` |
| Lock | `results/btc_ny_session_scalp_lock.json` |
| Result | `results/btc_ny_session_scalp_autoresearch.json` + `.md` |
| Overlay | `mql5/Indicators/BtcNySessionScalp.mq5` |
| Clock | `mql5/Include/BtcSessionUtils.mqh` |
| Runbook | `docs/HOWTO-BTC-NY-SESSION-SCALP.md` |

## 7. Non-goals

No `--live`. No `OrderSend`. No retune of this 96-cell grid. No Americas 16–24 UTC. No 4h RegimeRouter. No CVD. No CME-halt entries. No rewrite of `BtcTrendPullback`.
