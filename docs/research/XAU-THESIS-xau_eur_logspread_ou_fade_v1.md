# Thesis memo — `xau_eur_logspread_ou_fade_v1`

**Date:** 2026-09-18  
**Status:** FROZEN then develop screen (owner: “do it” on EUR–GBP–XAU OU pairs)

## Mechanism

Trade the **log-spread** `s = log(XAUUSD) − β log(EURUSD)`, not gold direction.

- `β` = OLS of log XAU on log EUR over the last **60** completed days (exclude today).
- `z` = (s_T − mean(s on that window)) / std(window), ddof=1.
- `|z| > 2` → fade the spread next day (both legs). Exit when `z` crosses **0**, or **20** calendar days, whichever first.
- Long spread = long 0.5 lot XAU, short EUR notional = `β ×` XAU notional.
- Short spread = opposite.
- Fill: next day’s first H1 open both books; exit first H1 open after exit signal.
- Never reshape EUR into an XAU-only indicator: **EUR is a traded hedge**, not a gate.

Control for gates: **always-flat** (NP>0 after costs). Always-long gold is **reported**, not a kill (this is not a drift book).

Soft: n≥40, PF≥1.2, NP>0, DD≤15%. Holdout sealed. 0 free knobs.

## Not

London FX cosign, DXY/DFII10 β follow, H4 pullback, GOLD_SCALP, Johansen 3-vector (deferred; 2-leg only).
