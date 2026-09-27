# Thesis memo — `eur_gbp_logspread_ou_fade_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **not run**  
**Charter:** `results/xau_charters/2026-09-19_eur_gbp_logspread_ou_fade_v1.json`  
**Tape:** Phase 0 `eurusd_h1.csv` ∩ `gbpusd_h1.csv` (2021-09-07 → develop `< 2026-01-01`)

## Why this family

Gold directional, event, residual, β, GARCH, GVZ, and **XAU–XAG** are dead vs sitting 0.5 lot (or two-leg DD blowup). MQL5 gold articles/signals reprint grid/breakout/long-gold. This book **leaves gold**. Payoff is EURUSD vs GBPUSD log-spread fade. FX B&H is ~0, so a fade can actually win. Not `eurusd_ny_scalp`. Not XAU–EUR OU.

## Rule (0 knobs)

1. Daily OHLC on **server date as stored**, inner join EUR∩GBP, `time < 2026-01-01`.
2. **β:** expanding OLS `log(EUR_close) ~ 1 + log(GBP_close)` on days **strictly before** the signal close, min **252**.
3. \(z = e/σ\) from that window. Signal at **close**; fill **next day open**.
4. Fade: \(z>2\) short spread (short 0.10 EUR, long GBP notional = β × EUR notional). \(z<-2\) long spread.
5. Exit: z crosses **0** or **5** trading days. No extra stop.
6. Costs: per-bar `spread` on **both** legs. Point 0.00001, contract 100 000. Slip=0 UNMEASURED. Commission 0. Swap unmodeled.
7. Control: **always-flat**. Report-only: always-long 0.10 EURUSD on the same window.

## Gates

n≥40, PF≥1.2, NP>0, DD≤15%. Holdout sealed (package has 2026 bars — unused).

## Falsifier

EUR–GBP residual is not mean-reverting after two FX round-trips, or n thin / DD>15%.

## Do not

Retune 252/2/5. Reopen EURUSD NY MR. Add XAU third leg. Peek 2026. `--live`. Compute PF in this freeze.
