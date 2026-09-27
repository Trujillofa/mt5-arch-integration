# `exog_eur_gbp_tvbeta_xau_long_or_flat_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** |

60-day rolling OLS EUR+GBP → long XAU next day iff pred>0; else flat; never short. Phase 0 intersection. STP slip=0 UNMEASURED.

| Arm | n | WR | PF | NP | DD |
|-----|--:|---:|---:|---:|---:|
| tv-β long-or-flat | 544 | 52.2% | 1.27 | +$57.2k | **56.7%** |
| Always-long 0.5 lot | 1 | — | — | **+$126.8k** | — |

Fails DD≤15% and **beat always-long**. PF≥1.2 is not enough: flattening vs EUR/GBP residual still donates the gold drift.

Do not retune lookback 60. Do not reopen DXY/DFII10 β or London cosign v4.
