# `xau_eur_logspread_ou_fade_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** |

XAU–EUR log-spread fade, both legs, β OLS 60d, \|z\|>2 / exit 0, max 20d, 0.5 XAU lot + EUR hedge.

| Arm | n | WR | PF | NP | DD |
|-----|--:|---:|---:|---:|---:|
| OU fade | **27** | 48.1% | **0.47** | **−$47.2k** | **472%** |

Fails n≥40, PF≥1.2, NP>0, DD≤15%. Mean-reverting the gold/euro residual paid spread and the 2021–25 gold drift vs EUR.

Do not retune 60/2/20. Do not add GBP as a third leg to salvage. Do not peek holdout.
