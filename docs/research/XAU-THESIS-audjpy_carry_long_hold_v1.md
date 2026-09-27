# Thesis memo — `audjpy_carry_long_hold_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **not run**  
**Charter:** `results/xau_charters/2026-09-19_audjpy_carry_long_hold_v1.json`  
**Article (context only):** [22175](https://www.mql5.com/en/articles/22175) carry/swap. Catalog PF is not evidence.

## Why this family

Gold books and EUR–GBP OU are dead. MQL5 gold catalog reprints grid/breakout. This payoff is **overnight interest**, not a price forecast. Always **long AUDJPY** (classic +carry vs JPY). Control is the **same long with swap=0** — carry must be the edge, not the AUD bull.

## Rule (0 knobs)

1. Always **long 0.10 AUDJPY**. Never short. No entry filter.
2. Daily OHLC on **server date as stored**. Enter first develop day’s open; hold through last develop close; flatten there.
3. **Swap:** Vantage `SYMBOL_SWAP_LONG` converted to USD/lot/night **at screen** (one read, not searched). Apply that **constant** every weekday night. **Wednesday = 3×** (triple swap). Weekends = 0 extra beyond Friday rollover as broker posts it (do not invent weekend days).
4. Costs: CSV spread on **entry and final flatten**. Slip=0 UNMEASURED. Commission 0.
5. Caveat: freeze-day swap ≠ 2021–25 policy path. Charter says so. Fail closed if swap long ≤ 0.

## Gates

NP>0 after spread+swap; DD≤15%; **NP strictly greater than identical long with swap=0**. Holdout `2026-01-01` unused.

## Falsifier

AUDJPY price path dominates; constant swap does not beat the no-swap arm, or DD>15%.

## Do not

Retune 0.10 / Wednesday×3. Short JPY as a second knob. Screen gold. Peek holdout. `--live`. Compute PF in this freeze.
