# Vantage research costs — account-matched

**Date:** 2026-08-10  
**Live account:** MT5 login **27496181** · **Standard STP** · leverage **500:1** · server **VantageMarkets-Live 5**

## Default (matches live account)

| Field | Value |
|-------|--------|
| Account type | **STANDARD_STP** |
| Commission | **$0** per side per lot (no separate commission) |
| Spread | **Measured** from this terminal (`xauusd_data.csv` / bridge dump) |
| H1 spread | median **18 pts** · p90 **21** · max **50** |
| Slippage | **0** (still unmeasured; demo fills only) |

Standard STP pays the broker in the **spread**, not a ticket commission. Charging RAW/PRO commission *on top of* this account’s measured spread would **double-count** relative to how 27496181 is billed.

**Official Vantage LATAM help (Standard STP):**
[What is a Standard STP account?](https://latam.vantagehelpcenter.com/hc/en-us/articles/12408090719119-What-is-a-Standard-STP-account)

Quoted characteristics:

- STP to liquidity providers (no dealing desk)
- Low spreads
- **No commission fees** (*excluding certain ETFs and stock products*)
- Other fees may still apply (swap, etc.)

XAUUSD on this account is a **metal CFD**, not the ETF/stock exclusion — research model stays **commission_per_lot = 0** + measured `MqlRates.spread`.

Source of truth: [`results/xau_research_costs.json`](xau_research_costs.json)  
Loader: [`scripts/xau_research_costs.py`](../scripts/xau_research_costs.py)

## Round-trip cost in `simulate()`

```
RT = (spread_pts + 2*slippage_points) * point_size * CONTRACT_SIZE * lots
   + 2 * commission_per_lot * lots
```

On Standard STP: `commission_per_lot = 0` → RT is spread (and optional slip) only.

## Alternatives (stress / other account types — not this login)

| Account type | commission_per_lot (per side) | When to use |
|--------------|-------------------------------|-------------|
| **STANDARD_STP** (live) | **0.0** | Default for research on 27496181 |
| PRO ECN | 1.5 | What-if if you moved to PRO |
| RAW ECN | 3.0 | What-if if you moved to RAW (usually tighter spread + commission) |

RAW/PRO are **not** this account. ECN would typically show a *different* spread distribution than the Standard dump already in the CSV.

## Dead bb_rsi baseline (docs only, fit window, no re-search)

| Scenario | PF | Net |
|----------|-----|-----|
| **Standard STP (live-matched)** | 1.6713 | $1188 |
| + PRO $1.50 stress | 1.6522 | $1160 |
| + RAW $3.00 stress | 1.6372 | $1139 |

See `results/xau_cost_sensitivity_vantage.json`.

## History note

2026-08-08 resume-edge temporarily set research default to RAW $3 as a conservative floor before the live account type was confirmed. **Corrected 2026-08-10** to Standard STP / commission 0 after owner reported account type on VantageMarkets-Live 5.
