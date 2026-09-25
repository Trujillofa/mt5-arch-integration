# Thesis memo — `xau_xag_logspread_ou_fade_v1`

**Date:** 2026-09-19  
**Status:** **FROZEN** · develop screen **BLOCKED_ON_DATA** until Vantage (or same-broker) **XAGUSD H1** from **2018-04-02**  
**Charter:** `results/xau_charters/2026-09-19_xau_xag_logspread_ou_fade_v1.json`  
**Article (context only):** [14035](https://www.mql5.com/en/articles/14035) XAG–XAU spread. Catalog PF is not evidence. Do **not** copy seasonal months from their chart.

## Why this family

Directional gold, FOMC, realized GARCH, and **GVZ implied-vol** sizing all lost to always-long 0.5 lot. This is **not** another gold sizer. Payoff is **market-neutral metals**: fade `log(XAU) − α − β log(XAG)`. Distinct from dead `xau_eur_logspread_ou_fade_v1` (FX residual). Control is **always-flat**; always-long XAU is report-only.

Vantage MCP `get_chart_history` **XAGUSD** (and SILVER / .r / m) returned **symbol not found** on 2026-09-19. Freeze anyway. Do **not** screen on gold-only.

## Rule (0 knobs)

1. Daily OHLC on **server date as stored** from H1, inner join XAU∩XAG, `time < 2026-01-01`.
2. **β:** expanding OLS `log(XAU_close) ~ 1 + log(XAG_close)` on days **strictly < D**, min **252** returns. No rolling 60 (that was the EUR book).
3. Residual \(e_D\) and σ from that window. \(z = e / σ\). Signal at **close**; fill **next day open**.
4. Fade: \(z>2\) → short spread (short 0.5 XAU, long XAG notional = β × XAU notional). \(z<-2\) → long spread. Never a third leg.
5. Exit: z crosses **0** or **5** calendar trading days, whichever first. No stop beyond that.
6. Costs: `xau_research_costs.json` on **both** legs (XAU spread from dump; XAG spread median-impute). Slip=0 UNMEASURED. Swap unmodeled both legs.
7. Frozen sizes: XAU lot **0.5**, contract 100 oz; XAG contract **5000** oz, point **0.001** (Vantage-typical; confirm at screen, do not search).

## Gates

n≥40, PF≥1.2, NP>0, DD≤15%. Always-long XAU is **not** a pass/fail gate (spread book). Holdout sealed.

## Falsifier

Gold/silver ratio trends; fade pays two spreads and loses. Thin n or DD blowup.

## Do not

Retune 252 / 2 / 0 / 5d. Copy article seasonal windows. Reopen XAU–EUR OU. Screen without XAG H1. Peek holdout. `--live`. Compute PF in this freeze.
