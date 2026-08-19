# US100 session-scalp develop screen (`us_index_session_develop_v1`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_develop_v1` (new family, not a retune of `ny_cash_orb_vwap_ema_flat`) |
| **Lock** | `results/us_index_session_develop_lock.json` |
| **Holdout** | **2026-06-01** — never used for selection |
| **Book** | $10,000 start, 1 lot, contract 1 |
| **Costs** | cache spread + 10 pt slippage/side, commission 0, US100 cap 200 pt |
| **Data** | FP `M5.hc` via CSV dump, 57,827 bars (2025-10-22 → 2026-08-18) |
| **Grid** | 1,728 configs (~53 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 615** eligible · top-20 holdout **0 / 20** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_autoresearch.json`.

---

## What was searched

OR 5/15/30 × EMA (5/13, 8/21, 9/21) × filters `orb_vwap_ema|orb_vwap|orb_ema|orb_only` × entry end 10:30/11:30/12:00 × one-per-day T/F × exits flatten 11:30/12:00/15:45, ATR 1.0/1.5, 1.5/2.0, 1.0/2.0, bars 6/12.

Eligible = develop net > 0 and ≥ 40 trades. Rank = profit factor then expectancy. Holdout scored only after the ranking froze.

---

## Goals missed

On this book, 1%/day and 20%/month need roughly **$100/day** and **$2,000/month** at the *median*. The best develop config is about **0.40% median daily** and **1.89% median monthly** — ~2.5× short of the daily goal and ~10× short of the monthly goal. **6%** of its develop trade-days reached 1%. **0** months reached 20%.

Holdout (29 trades, 3 months) is thinner still: median daily **−0.28%**, monthly 1.36%. Do not treat the develop PF 2.19 as an edge that survived.

This is not a sizing problem to paper over. 1 lot on $10k is already aggressive for US100 cash. Larger lots would scale both P&L and drawdown; they would not invent a 20% median month from a 1.9% one.

---

## Best develop (then scored on holdout)

OR **5**, EMA **8/21**, `orb_vwap_ema` (tied with `orb_ema` — VWAP was non-binding), entry **10:30**, one/day, exit **ATR SL 1.0 / TP 1.5**.

| Window | n | WR | PF | Net | Median day | Median month |
|--------|--:|---:|---:|----:|-----------:|-------------:|
| Develop (before 2026-06-01) | 98 | 58% | 2.19 | +$1,959 | **0.40%** | **1.89%** |
| Holdout (from 2026-06-01) | 29 | 48% | 1.49 | +$362 | **−0.28%** | 1.36% |

The entire top 10 is the same ATR 1.0/1.5 exit. Flatten-to-15:45 never ranks (matches the first flatten replay: MAE > MFE). `orb_vwap_ema` and `orb_ema` print identical rows — VWAP did not change the set.

---

## Top 10 develop (holdout after selection)

| # | OR | EMA | Filter | Window | Exit | Dev PF | Dev day | Dev mo | HO PF | HO day |
|--:|---:|-----|--------|--------|------|-------:|--------:|-------:|------:|-------:|
| 1 | 5 | 8/21 | orb_vwap_ema | 10:30 | ATR 1.0/1.5 | 2.19 | 0.40% | 1.89% | 1.49 | −0.28% |
| 2 | 5 | 8/21 | orb_ema | 10:30 | ATR 1.0/1.5 | 2.19 | 0.40% | 1.89% | 1.49 | −0.28% |
| 3 | 5 | 9/21 | orb_vwap_ema | 10:30 | ATR 1.0/1.5 | 2.00 | 0.37% | 1.46% | 1.50 | −0.28% |
| 4 | 5 | 9/21 | orb_ema | 10:30 | ATR 1.0/1.5 | 2.00 | 0.37% | 1.46% | 1.50 | −0.28% |
| 5 | 5 | 5/13 | orb_vwap_ema | 10:30 | ATR 1.0/1.5 | 1.99 | 0.38% | 1.55% | 1.07 | −0.40% |
| 6 | 5 | 5/13 | orb_ema | 10:30 | ATR 1.0/1.5 | 1.99 | 0.38% | 1.55% | 1.07 | −0.40% |
| 7 | 15 | 5/13 | orb_vwap_ema | 10:30 | ATR 1.0/1.5 | 1.90 | 0.37% | 1.29% | 1.10 | −0.38% |
| 8 | 15 | 5/13 | orb_ema | 10:30 | ATR 1.0/1.5 | 1.90 | 0.37% | 1.29% | 1.10 | −0.38% |
| 9 | 5 | 5/13 | orb_vwap_ema | 11:30 | ATR 1.0/1.5 | 1.87 | 0.35% | 1.55% | 1.07 | −0.40% |
| 10 | 5 | 5/13 | orb_ema | 11:30 | ATR 1.0/1.5 | 1.87 | 0.35% | 1.55% | 1.07 | −0.40% |

---

## What this does **not** authorize

- Do **not** replace frozen overlay defaults (`OR 15`, EMA `9/21`, window to `11:30`).
- Do **not** promote, `--live`, or attach an order EA.
- Do **not** expand this grid or retune on holdout to chase 1%/20%.
- A tighter-exit family, if ever wanted, is a **new** `search_id` with a new freeze-before-peek — not another pass on this CSV.

Indicator v1.30 adds **optional** entry-end + ATR SL/TP guides so the candidate can be *observed*. Those inputs stay off / frozen unless you flip them by hand.
