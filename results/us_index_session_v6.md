# US100 v6 screen (`us_index_session_v6`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_v6` — daily Hurst/ADX/ATR regime switch + London XAU risk gate |
| **Lock** | `results/us_index_session_v6_lock.json` |
| **Select** | `et_date < 2026-06-01` |
| **Holdout** | **2026-07-01** onward. June unused (burned). July–August already sat inside the v4/v5 holdout aggregates — cleaner window, **not virgin**. |
| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |
| **Grid** | 136 configs (128 regime + 8 London gate; ~3 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 4** eligible · top-20 holdout **0 / 4** |
| **Eligible by family** | `daily_regime_switch` **0** · `london_xau_fx_risk_gate` **4** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_v6.json`.

Architectural reset after v1–v5. Not a retune. Not an XAU charter. These families stay **Python-only**.

---

## What was read from `~/Projects/trading` (before the lock)

| Kept | Rejected |
|------|----------|
| NY cash clock + causal 15m OR + `prior_cash_close_series` / `cash_open_gap_pct` | v1–v5 winners as defaults |
| Wilder ADX algorithm from `manual-trading-agent/src/indicators/adx.py` (rewritten as a causal daily series) | manual-trading-agent vol-regime / news-drift (DISCARD; calendar ends 2025-04-07 Tehran) |
| Completed-ET-day grammar from `completed_h4_ema_bias` / `completed_daily_donch_state` | Daily.hc / H4.hc (`read_mt5_hc_m5` rejects step>3600) |
| Exog *shape*: as-of `feature_end <= m5_bar_open`, predictor-only sign, T* isolation | `exog_london_fx_cosign_xau_follow_flat` hours `{7,8,9}` (server 07:00 ≈ **midnight ET** on FP) |
| FP `XAUUSD.r` H1.hc, same prefix, offset 10800 → UTC → `America/New_York` 07:00–09:00 | Vantage `instrument_data/*_h1.csv` and `xauusd_data.csv` (`+00:00` is not UTC; do not naive-join) |
| crypto-agent MTF *join idea* (HTF state first) | `multi_timeframe_regime` as an edge (failed / stub) |
| | `ctrader` SessionClock NY 08:00–17:00 (FX, not cash 09:30) |
| | US30 as predictor (v5: same trade) |
| | EURUSD/GBPUSD H1.hc — live cache ends 2026-08-14 12:00 ET while US100 runs through 2026-08-18 |

No Hurst stack existed in `~/Projects/trading`. R/S + locked variance-ratio fallback (`k=2`; VR>1 → 0.56, VR<1 → 0.44) were frozen **before** any Hurst was computed on this CSV.

Family 2 **ran** on FP XAUUSD.r (219 London-feature days). FX predictors were skipped, not the family.

---

## Goals missed

Best develop (London XAU risk-on/off gates the 15m OR close-break; `|disp| ≥ 0.5 ATR`; EMA21 trail; flatten 15:45):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 48 | 46% | 1.49 | **−0.038%** | **−0.17%** |
| Holdout (from 2026-07-01) | 11 | 45% | 3.14 | **−0.19%** | +2.84% |

Net is positive because of a fat right tail (mean day +0.09%). The **median** trade-day is still negative. 8% of develop days were ≥1% — that is not a 1% median.

| Family | Eligible | Best develop | Holdout |
|--------|----------|--------------|---------|
| london_xau_fx_risk_gate | 4 / 8 | PF 1.49 · **−0.038%** day · 48 trades | PF 3.14 · **−0.19%** day |
| daily_regime_switch | **0 / 128** | 5 trades (all momentum, 0 MR) · PF 3.08 · **−0.06%** day | 4 trades · median day +0.79% (PF undefined; n too small) |

The AND-gate (ADX>25 ∧ ATR>60th ∧ Hurst>0.55, else ADX<20 ∧ ATR<40th ∧ Hurst<0.45, else chop) starved the book. Five develop trades cannot pass the ≥40-trade gate. Mean-reversion never fired on the displayed config.

0% of develop trade-days on the winner were a 1% median. The reset did not create a 1%/20% engine on this book.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not put regime-switch or the London XAU gate on the overlay.
- Do not stamp Vantage `{7,8,9}` onto FP US100.
- Do not naive-join Vantage H1 to FP M5.
- Do not reopen news-drift, Timescale, M1, or US500.
- Do not cut slippage or raise lots.
- Do not retune these 136 configs. A later idea is a **new** `search_id` with a new freeze-before-peek.
