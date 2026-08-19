# US100 v5 screen (`us_index_session_v5`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_v5` — cash-open gap fade, HTF-locked OR, US30→US100 follow |
| **Lock** | `results/us_index_session_v5_lock.json` |
| **Select** | `et_date < 2026-06-01` |
| **Holdout** | **2026-07-01** onward. June unused (burned). July–August already sat inside the v4 holdout aggregate. |
| **Book** | $10,000 / 1 lot. Slippage **kept** at 10 pt/side. |
| **Grid** | 120 configs (~8.5 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 43** eligible · top-20 holdout **0 / 20** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_v5.json`.

Not a retune of v1–v4. Not an XAU charter. These families stay **Python-only**.

---

## What was read from `~/Projects/trading` (before the lock)

| Kept | Rejected |
|------|----------|
| NY cash clock + causal 15m OR (`us_index_session_core.py`) | v1–v4 winners as defaults |
| Gap = **09:30 open / prior cash close** (median \|gap\| ~0.60% on this tape). Last pre-09:30 print is ~0 | Defining “gap” as the 09:30 jump |
| BTC `CompletedHtfShift` + XAU `shift(1)` H4 join; Daily Donchian **excluding** the last completed day | Daily SMA200 (warmup eats develop). XAU Donchian as a turtle entry (`KILL_DONCHIAN_LINE`) |
| Exog *shape*: intersection I, predictor-only sign, next-bar follow, traded T* isolation | `exog_london_fx_cosign_xau_follow_flat` hours `{7,8,9}` / EUR+GBP (Vantage H1, server 07:00 ≈ **midnight ET** on FP) |
| US30 M5 already on disk, 57,821-stamp intersection | `us100_us30_divergence` HH/LH fade (v3). Joint 3-book fade (SCREEN_FAIL). News-drift DISCARD. Yields / ES / US500 / Timescale (no files) |

IB is **not** the failed 15m OR signal. `after_ib` waits until 10:30 and skips if the gap already filled.

---

## Goals missed

Best develop (15m OR close-break, **completed H4 EMA50/200 must match**, one/day, to 11:30, ATR 1.0/1.5):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 58 | 60% | 2.23 | **0.40%** | **2.16%** |
| Holdout (from 2026-07-01) | 15 | 27% | 0.60 | **−0.46%** | −1.15% |

HTF locking raised in-sample PF vs v4 (1.51 → 2.23) and cut trade count (107 → 58). The holdout went the other way (PF 1.07 → 0.60). That is a stricter filter on the same OR break, not a new median-day engine.

| Family | Best develop | Holdout |
|--------|--------------|---------|
| htf_lock_orb | PF 2.23 · 0.40% day | PF 0.60 · **−0.46%** day |
| ny_cash_gap_fade_adr | 0.26% day (0.5–2.0% gap, ADR14≥0.4, next bar) | **−0.36%** day |
| exog_us30_ny_cash_cosign_us100_follow | 0.18% day (US30 \|move\|≥0.35 ATR, flatten 15:45) | **−0.07%** day |

0% of develop trade-days on the winner were ≥1%. The architectural shift did not create a 1% median day on this book.

---

## What this does **not** authorize

- Do not promote, `--live`, or attach an order EA.
- Do not put gap / HTF-lock / US30-follow on the overlay.
- Do not stamp Vantage `{7,8,9}` onto FP US100.
- Do not reopen news-drift, Timescale, M1, or US500.
- Do not cut slippage or raise lots (already tested; 0.002 pp / leverage only).
- A later idea is a **new** `search_id` with a new freeze-before-peek.
