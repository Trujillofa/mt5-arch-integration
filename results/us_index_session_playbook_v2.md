# US100 playbook screen (`us_index_session_playbook_v2`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_playbook_v2` — VWAP bounce + EMA/MACD (new families) |
| **Lock** | `results/us_index_session_playbook_v2_lock.json` |
| **Holdout** | **2026-06-01** — never used for selection |
| **Book** | $10,000 start, 1 lot, contract 1 |
| **Costs** | cache spread + 10 pt slippage/side, US100 cap 200 pt |
| **Grid** | 528 configs (~13 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 205** eligible · top-20 holdout **0 / 20** |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_playbook_v2.json`.

This is **not** a retune of `ny_cash_orb_vwap_ema_flat` or `us_index_session_develop_v1`.

---

## Families (from the playbook, frozen before the run)

**`ny_cash_vwap_bounce_rsi`** — first 30–60 minutes of NY cash (from 09:35 ET). Fade an ATR-sized close-vs-VWAP extension when Wilder RSI is exhausted. Target is VWAP **frozen at the signal close**. Fill = next bar open.

**`ny_cash_ema_macd`** — closed-bar fast EMA cross (5/20 or 8/21) with MACD histogram filter (12/26/9 or 5/13/5). Cross-only and stacked variants. Fill = next bar open.

US30 is a **transfer check** after US100 ranking — never used for selection.

---

## Goals missed

Best develop (VWAP bounce, RSI 7, 70/30, 1.0 ATR, window to 10:00, VWAP target + 1.0 ATR SL):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 42 | 57% | 2.11 | **0.31%** | **0.87%** |
| Holdout | 16 | 38% | 0.81 | **−0.39%** | −0.20% |

**0%** of those develop trade-days reached 1%. No month reached 20%. Holdout is net negative. The develop PF does not survive.

Best EMA/MACD (5/20, MACD 12/26/9, cross, flatten 11:30): develop PF 1.76 / median day **0.22%**; holdout PF **0.72**.

US30 transfer of the US100 winner: develop median day **−0.11%**; holdout PF 4.57 on **18** trades. That holdout is not a select and does not authorize a promote.

---

## Top 10 develop (holdout after selection)

| # | Family | Window | Setup | Exit | Dev PF | Dev day | HO PF | HO day |
|--:|--------|--------|-------|------|-------:|--------:|------:|-------:|
| 1 | VWAP bounce | 10:00 | RSI 7 70/30 · 1.0 ATR | VWAP+SL1 | 2.11 | 0.31% | 0.81 | −0.39% |
| 2 | VWAP bounce | 10:30 | RSI 7 70/30 · 1.5 ATR | ATR 1.0/1.5 | 1.87 | 0.29% | 0.62 | −0.37% |
| 3 | VWAP bounce | 10:30 | RSI 7 70/30 · 1.5 ATR | VWAP+SL1 | 1.81 | −0.13% | 0.62 | −0.42% |
| 4 | VWAP bounce | 10:30 | RSI 7 70/30 · 1.0 ATR | VWAP+SL1 | 1.76 | 0.28% | 1.10 | −0.36% |
| 5 | EMA/MACD | 10:30 | 5/20 · 12/26/9 · cross | flatten 11:30 | 1.76 | 0.22% | 0.72 | −0.10% |
| 6 | EMA/MACD | 10:30 | same, one/day off | flatten 11:30 | 1.76 | 0.22% | 0.72 | −0.10% |
| 7 | EMA/MACD | 10:30 | 5/20 · 12/26/9 · cross | bars 12 | 1.72 | 0.14% | 0.77 | −0.15% |
| 8 | EMA/MACD | 10:30 | same, one/day off | bars 12 | 1.72 | 0.14% | 0.77 | −0.15% |
| 9 | VWAP bounce | 10:30 | RSI 7 70/30 · 1.0 ATR | ATR 1.0/1.5 | 1.58 | 0.26% | 0.91 | −0.37% |
| 10 | EMA/MACD | 11:30 | 5/20 · 12/26/9 · cross | flatten 11:30 | 1.55 | 0.08% | 0.82 | +0.07% |

---

## What this does **not** authorize

- Do **not** replace frozen overlay defaults.
- Do **not** promote, `--live`, or attach an order EA.
- Do **not** expand this grid, retune on holdout, or “trade the US30 transfer.”
- A later idea is a **new** `search_id` with a new freeze-before-peek.

Indicator v1.40 adds optional `InpFamily` observe modes. Default stays the frozen ORB combo.
