# Thesis memo — `xau_cot_gc_mm_fade_long_or_flat_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **not run** · COT file **not fetched**  
**Charter:** `results/xau_charters/2026-09-19_xau_cot_gc_mm_fade_long_or_flat_v1.json`  
**XAU tape:** `results/xau_fomc_h4/xauusd_h1_2018_2025.csv`  
**COT:** CFTC Disaggregated, `GOLD - COMMODITY EXCHANGE INC.` — fetch **at screen**, not this freeze.

## Why this family

Retail TA, residuals, GARCH/GVZ, FOMC, and XAU–XAG are dead vs always-long. Tick/IV-surface/GOFO are out of this Wine prefix. **COT is the one free exogenous series** we can join to the Vantage dump.

Spot XAU has no COT. Map **COMEX GC** managed-money net % open interest onto Vantage XAU. Still **long-or-flat vs always-long** — likely dies; untested.

## Rule (0 knobs)

1. Report: CFTC **Disaggregated Futures-Only**, contract **GOLD - COMMODITY EXCHANGE INC.** As-of **Tuesday**. Released **Friday ~15:30 America/New_York**. Never trade Tuesday on Tuesday’s file.
2. Managed-money net % OI = `(MM_long − MM_short) / open_interest × 100`.
3. Expanding z: this week’s net % vs mean/std of reports with **as-of Tuesday strictly before** this Tuesday. Min **52** weeks. Skip if std=0.
4. **Signal Friday close** (after release). **Fill next XAU daily open** (server date as stored).
5. Long **0.5 lot** when z **< −2**. Flatten when z **> −0.5**. Never short. One position.
6. Costs: `results/xau_research_costs.json` on entries/exits. Median-impute missing spread. Slip=0 UNMEASURED. Swap unmodeled (same as always-long control).
7. Control: always-long 0.5 lot, **same first-eligible day through last develop day**.

## Gates

n≥40, PF≥1.2, NP>0, DD≤15%, **must beat always-long net**. Holdout `2026-01-01` unused.

## Falsifier

Weekly commercials/specs do not beat sitting 0.5 lot after costs, or n thin.

## Do not

Retune −2 / −0.5 / 52w. Legacy two-bucket COT. Short specs. Tick/Bookmap. Peek holdout. `--live`. Compute PF or download COT in this freeze.
