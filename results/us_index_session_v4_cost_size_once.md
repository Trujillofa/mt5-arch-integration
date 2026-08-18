# One-shot cost/size diagnostic (`us_index_session_v4_cost_size_once`)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Kind** | Diagnostic **replay** — not a search |
| **Lock** | `results/us_index_session_v4_cost_size_once_lock.json` |
| **Replayed** | Frozen ORB flatten 15:45 · v4 develop winner (`vol_regime_orb` ATR 7>28, one/day, to 10:30, ATR 1.0/1.5) |
| **Skipped** | TimescaleDB · M1 export · US500 |
| **Books** | locked 1 lot / 10 pt · slip 0 · 2 lots · 5 lots · slip 0 + 5 lots |
| **Goals** | median trade-day ≥ **1%** and median month ≥ **20%** on the $10k book |
| **Hits** | **0 / 5** books · **0** window with both goals |
| **promote / live_go** | **no / false** |

Machine JSON: `results/us_index_session_v4_cost_size_once.json`.

The locked $10k / 1-lot / 10 pt book is **unchanged**. Indicator defaults stay frozen.

---

## What this was allowed to test

Slippage and lots only, on **already-selected** params. Not a new grid. Not a retune.

Timescale / M1 / US500 stayed out: this repo has no tick store, M1 was not exported, US500 is not in any Wine prefix.

---

## Result: 1%/20% is not a friction or size problem

Cutting 10 pt/side slippage moves median day by about **0.002 percentage points**. Spread in the M5 cache is still charged. Friction is not the wall.

Raising lots **scales the same edge**. Profit factor does not change. At 5 lots, v4 develop median day becomes **1.53%** (daily goal only) and median month is **7.5%** — still far from 20%. The same 5-lot book prints v4 holdout median day **−2.01%**. Frozen flatten at 5 lots loses **$15k** in develop (PF 0.72).

| Book | Frozen develop day / month | Frozen holdout day | v4 develop day / month | v4 holdout day |
|------|----------------------------|--------------------|------------------------|----------------|
| locked (1 / 10 pt) | −0.16% / −4.8% | +0.41% | **0.31% / 1.50%** | **−0.40%** |
| slip 0 | −0.16% / −4.8% | +0.41% | 0.31% / 1.53% | −0.40% |
| 2 lots | −0.32% / −9.7% | +0.81% | 0.61% / 3.01% | −0.80% |
| 5 lots | −0.79% / −24.2% | +2.04% (day only) | **1.53% / 7.52%** (day only) | **−2.01%** |
| slip 0 + 5 lots | −0.78% / −24.0% | +2.05% (day only) | 1.54% / 7.65% (day only) | −2.00% |

No row hits both goals. The 5-lot daily “hit” is leverage on a ~0.3% in-sample median, and the holdout gets worse in proportion.

---

## What this does **not** authorize

- Do not replace the locked book with 0 slippage or 5 lots.
- Do not promote, `--live`, or attach an order EA.
- Do not treat this as a reason to export M1 or add Timescale/US500.
- Do not retune v1–v4 winners on holdout.
