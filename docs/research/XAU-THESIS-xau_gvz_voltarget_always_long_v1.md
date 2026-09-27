# Thesis memo — `xau_gvz_voltarget_always_long_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **not run**  
**Charter:** `results/xau_charters/2026-09-19_xau_gvz_voltarget_always_long_v1.json`  
**Tape:** `results/xau_fomc_h4/xauusd_h1_2018_2025.csv` + FRED **GVZCLS** (fetch at screen, not this freeze)  
**Article (context only, not evidence):** [23734](https://www.mql5.com/en/articles/23734) — observe-only GLD IV vs XAU RV. Catalog PF is not a reason.

## Why this family

GARCH(1,1) **realized** vol-target on the always-long host **SCREEN_FAIL** (Calmar 3169 vs 3241; mean lots 0.473). Sitting still wins. This family keeps the **same host and the same 15% target** but sizes from **implied** vol: CBOE Gold ETF volatility index (**GVZ** / FRED `GVZCLS`), the historical stand-in for the article’s live options feed.

Different information set, not a retune of ω/α/β. The article is a monitor, not a book; we do **not** copy its 1.20 / 1.05 / 0.95 flatten cuts (unestimated heuristics).

## Rule (0 knobs)

1. **Host:** always long XAU. Never short. Never a new entry rule.
2. **Clock:** resample H1 → **daily** OHLC on the **server date as stored**. Size at **day D open**.
3. **GVZ:** FRED `GVZCLS` daily close, already in **percent** (26.9 means 26.9% ann, not 0.269). **As-of join:** last GVZ with **date strictly < D**. No same-day peek. If none exists, **flat**.
4. **Lots:** \(\min\bigl(0.5,\; \mathrm{floor}_{0.01}(0.5 \times 15 / \mathrm{GVZ}_{<D})\bigr)\). Below 0.01 → flat. Cap 0.5. Target **15%** frozen (same number as dead GARCH, not a search).
5. **Costs:** `results/xau_research_costs.json` on lot changes and final flatten. Median-impute missing spread. Slip=0 UNMEASURED. **Swap unmodeled both arms.**
6. **Control:** constant **0.5 lot** always-long on the **same days** the GVZ arm is eligible to size (first day a prior GVZ exists through last develop day).

## Gates (develop, holdout sealed)

Pass only if **all**: net profit \(> 0\); max DD **strictly below** control; Calmar (net / max DD%) **strictly above** control. Else **SCREEN_FAIL**. No refine.

## Falsifier

Implied vol just deleverages the bull the same way realized GARCH did.

## Do not

Retune 15% or GVZ units. Copy article 1.20 flatten. EGARCH / H1 GARCH salvage. Attach to FOMC, H4, OU, Renko, GOLD_SCALP. Screen `xauusd_data.csv`. Peek holdout. `--live`. Compute develop metrics in this freeze commit. Vendor the article’s MQL service.
