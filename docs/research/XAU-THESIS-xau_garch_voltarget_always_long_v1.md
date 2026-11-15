# Thesis memo — `xau_garch_voltarget_always_long_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **not run**  
**Charter:** `results/xau_charters/2026-09-19_xau_garch_voltarget_always_long_v1.json`  
**Tape:** `results/xau_fomc_h4/xauusd_h1_2018_2025.csv` (Vantage MCP H1, 2018-04-02 → 2025-12-31)

## Why this family

Directional gold, event windows, residuals, β, and a Renko event-clock of vendor ADX/BB are dead vs **always-long 0.5 lot**. Sitting is the only book that made money. This family does **not** pick entries. It is a **risk module on that host**: GARCH(1,1) vol-target the same always-long path and ask whether path/DD improves after Standard STP costs.

MATH-MODELS-ROADMAP item 1 (GARCH as filter, not direction). Always-long is the open host.

## Rule (0 knobs)

1. **Host:** always long XAU. Never short. Never a new entry rule.
2. **Clock:** resample H1 → **daily** OHLC on the **server date as stored** (first open, max high, min low, last close). Not ET. Not H1 GARCH.
3. **Returns:** \(r_t = \ln(C_t / C_{t-1})\) on daily closes.
4. **Model:** Gaussian GARCH(1,1)  
   \(\sigma^2_t = \omega + \alpha r_{t-1}^2 + \beta \sigma_{t-1}^2\), \(\omega>0\), \(\alpha\ge 0\), \(\beta\ge 0\), \(\alpha+\beta<1\).  
   Expanding-window MLE on returns with **date < D**. First size after **252** daily returns. Refit once per day. One-step \(\hat\sigma_D\) sizes **day D open**.
5. **Target:** **15%** annualized, frozen. \(\hat\sigma_{\mathrm{ann}} = \hat\sigma_D \sqrt{252}\).
6. **Lots:** \(\min\bigl(0.5,\; \max\bigl(0,\; 0.5 \times 0.15 / \hat\sigma_{\mathrm{ann}}\bigr)\bigr)\), floored to 0.01. Below 0.01 → **flat that day** (vol targeting, not a directional filter). Cap 0.5.
7. **Costs:** `results/xau_research_costs.json` on **lot changes** (initial entry, rebalance, final flatten). Spread from the dump (median-impute missing). Slip=0 UNMEASURED. **Swap unmodeled on both arms** (both hold overnight).
8. **Control:** constant **0.5 lot** always-long on the **same post-warmup window**, same costs.

## Gates (develop, holdout sealed)

Not a trade-count PF book. Pass only if **all**:

- net profit \(> 0\)
- max DD **strictly below** constant-lot DD
- Calmar (net / max DD%) **strictly above** constant-lot Calmar

Fail any → **SCREEN_FAIL**. No refine.

## Falsifier

Vol targeting only deleverages the bull: net and Calmar lose to 0.5 lot (or DD does not improve).

## Do not

Retune 15% / 252 / GARCH(1,1). Switch to EGARCH/GJR/H1. Attach this sizer to FOMC, H4 pullback, OU, Renko, GOLD_SCALP, or any dead `family_id`. Screen `xauusd_data.csv` (2021-only). Peek holdout. `--live`.
