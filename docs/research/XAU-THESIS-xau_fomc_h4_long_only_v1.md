# Thesis memo — `xau_fomc_h4_long_only_v1`

**Date:** 2026-09-18  
**Status:** **FROZEN** · develop screen **BLOCKED_ON_DATA** until H1 from **2018-01-01**  
**Charter:** `results/xau_charters/2026-09-18_xau_fomc_h4_long_only_v1.json`  
**Events:** `results/xau_fomc_scheduled_v1.csv` (Fed scheduled statements only)

## Why this family

Gold’s clean impulses are often **around the FOMC statement**, not London OR.  
2021–25 alone cannot test “long-or-flat vs always-long” (one bull). This freeze **requires** 2018+ (includes 2018 and 2022 dumps).

## Rule (0 knobs)

1. Event = **scheduled** FOMC *statement* at **14:00 America/New_York** (CSV dates). Exclude unscheduled (e.g. Mar 2020) and notation votes (2025-08-22).
2. H4 bars resampled from Vantage H1 (`floor 4h`, `server_clock_as_stored`).
3. Find the H4 bar whose **[open, next open)** contains that UTC instant. **Signal at that H4 close** (print already out). **Fill next H4 open**. Skip if open through SL.
4. **Long only.** Never short. No surprise sign.
5. Hold **8 H4 bars** (~32h) or SL **1.5 × ATR(H4,14)** at signal (SL wins), else flatten at close of bar 8.
6. Lots: risk 1% of 10k, cap 0.5. Costs: `xau_research_costs.json`.
7. Control: always-long 0.5 lot on the **same 2018+ develop window**. Must beat it on develop **and** n≥40, PF≥1.2, NP>0, DD≤15%.

CPI is a **sister**, not this freeze.

## Data gate

`xauusd_data.csv` H1 currently starts **2021-09-03**. Do **not** screen on that sample.  
Need H1 `time >= 2018-01-01` (Dukascopy/Vantage dump). Until then: **BLOCKED_ON_DATA**, not a fail, not a pass.

## Falsifier

FOMC windows are real but too rare / not excess enough vs sitting through 2018–25 gold.

## Do not

Retune 8 bars / 1.5 ATR / add CPI or NFP to salvage. Peek holdout. Screen the 2021-only bull. `--live`. GOLD_SCALP. Surprise-direction (needs a different family + forecast file).
