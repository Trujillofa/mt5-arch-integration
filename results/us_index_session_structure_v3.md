# US100 structure screen (`us_index_session_structure_v3`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Search** | `us_index_session_structure_v3` — sweep / FVG / US100–US30 divergence |
| **Lock** | `results/us_index_session_structure_v3_lock.json` |
| **Holdout** | **2026-06-01** — never used for selection |
| **Book** | $10,000 start, 1 lot |
| **Grid** | 240 configs (~20 s) |
| **Goals** | median trade-day ≥ **1%**, median month ≥ **20%** |
| **Hits** | develop **0 / 129** eligible · top-20 holdout **0 / 20** |
| **News family** | **skipped** (see below) |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_structure_v3.json`.

Not a retune of `ny_cash_orb_vwap_ema_flat`, `develop_v1`, or `playbook_v2`.

---

## What was tested

**`ny_cash_liquidity_sweep`** — after 09:45 ET, breach Asia, London-pre-NY, PDH/PDL, or the 15m OR, then close back inside with wick ≥ 25% or 40% of the M5 bar. Target opposite side of that box, 1.5× width, flatten 11:30, or ATR 1.0/1.5.

**`ny_cash_fvg_mitigation`** — M5 3-bar FVG, later close that touches 50% CE and closes away. No M1 micro-confirm (M1 is on disk in FP `M1.hc` but not in the locked CSV).

**`us100_us30_divergence`** — same-bar HH/LH vs US30 over 3/6/12 M5 bars. Named honestly: **no US500** in the FP prefix. Pair = both legs; `us100_only` fades US100.

---

## Why `macro_news_fix_api` was not run

`manual-trading-agent` news is a **calendar lockout + a gitignored HuggingFace Forex Factory scrape**, not a millisecond feed.

- Pinned CSV ends **2025-04-07**. This US100 window starts **2025-10**. **0 rows** to join.
- `DateTime` is **Asia/Tehran**, often midnight — not 08:30 ET. Using `Actual` at that stamp is lookahead.
- Live Faireconomy XML is **this week only**.
- FX surprise-drift in that repo is **DISCARD** (OOS net PF 0.375). Do not copy the 30m/4h follow-through.

A real news scalp needs an official BLS/Fed clock and prints inside this window. That data is not in either repo.

---

## Goals missed

Best develop (sweep PDH+OR, wick 0.40, to 10:30, multi/day, opposite box):

| Window | n | WR | PF | Median day | Median month |
|--------|--:|---:|---:|-----------:|-------------:|
| Develop | 66 | 52% | 2.29 | **0.17%** | **2.07%** |
| Holdout | 27 | 30% | 1.44 | **−0.45%** | 1.20% |

Holdout PF > 1 with a **negative median day** means a few large winners, not a typical 1% day. **0** months hit 20%.

| Family | Best develop | Holdout |
|--------|--------------|---------|
| Sweep | PF 2.29 · 0.17% day | PF 1.44 · **−0.45%** day |
| FVG | PF 1.03 · 0.11% day | PF 1.09 · 0.21% day |
| US100/US30 div (US100 only) | PF 1.47 · 0.11% day | PF 1.11 · −0.08% day |

The whole top 10 is PDH/OR sweep. Asia/London boxes did not rank. FVG is ~breakeven after costs. Divergence does not pay the goal.

---

## What this does **not** authorize

- Do not replace frozen overlay defaults.
- Do not promote, `--live`, or attach an order EA.
- Do not reopen the discarded FX news-drift lane.
- Do not export M1 or add US500 to chase 1%/20% on this CSV.
- A later idea is a **new** `search_id` with a new freeze-before-peek.

PDH and OR are already on the chart (v1.40). That is enough to *watch* a sweep. It is not a signal change.
