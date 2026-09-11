# BtcTrendPullback — first offline lock (H1 / H4)

| Field | Value |
|-------|--------|
| **Date** | 2026-09-11 |
| **Status** | Overlay already on main (buffer 7); develop screen **SCREEN_PASS_CANDIDATE** with **promote=no** |
| **Search** | `btc_trend_pullback_develop_v1` |
| **Lock** | `results/btc_trend_pullback_lock.json` |
| **Winner holdout** | n=0 (unevaluable) |
| **A-priori cell** | develop PF 0.94; null frac 0.60 |
| **promote / live_go** | **no / false** |

> Not `BtcNySessionScalp` (M5 NY-desk box, SCREEN_FAIL). This lane validates the *existing* H1/H4 overlay grammar. Do **not** edit `results/xau_loop_status.md`.

## Why this exists

`BtcTrendPullback.mq5` was the only mt5-arch indicator with zero offline lock/PF. The grammar is crypto-agent TrendPullback DNA compressed to H1 with a completed-H4 EMA50/200 bias. `DECISION_ABANDON_BTC_REGIME.md` recommended archiving the 4h multi-AND router — this is a different product (H1 pullback reclaim, not that router).

## Clock

Same ET+7 rule as BTC-NY. Admitted lag-0 vs Binance H1 (2021–24 corr 0.960 ≥ 0.95 floor; 2026 0.917 is the CFD/spot residual, unique lag-0 peak). No session box.

## Frozen search

192 configs: 3 families × SL {1.5, 2.0} ATR × TP {1.5, 2.0} R × time-stop {24, 48} H1 bars × ATR% {0.5%, 1%} × one-per-day × long-only. Holdout `et_date >= 2026-04-01` (137 days, asserted ∉ the taken set).

| Family | Thesis |
|--------|--------|
| `btc_h4bias_h1_pullback_reclaim` | H4 bias + near-EMA50 + RSI/MACD recovery |
| `btc_h4bias_h1_continuation` | strong H4 + not extended + momentum |
| `btc_h4bias_h1_full_grammar` | shipped default: pullback **or** continuation |

## Result

91/192 develop-eligible. Rank (PF then expectancy) picked a 44-trade full_grammar slice (PF 1.42) whose holdout is empty. The shipped-default analog loses (PF 0.94) and fails its own null (frac 0.60). **promote=no.** Overlay stays observe-only, buffer 7, untouched.
