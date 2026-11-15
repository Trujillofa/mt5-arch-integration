# `xau_h4_pullback_weekly_long_only_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** (not for selection; not evaluated) |
| **charter** | `results/xau_charters/2026-09-17_xau_h4_pullback_weekly_long_only_v1.json` SHA `d1fd6253…ead5da0` |
| **n_free_knobs** | 0 |

## Develop (`time < 2026-01-01`, Vantage H1→H4, Standard STP slip=0 UNMEASURED)

| Arm | n | WR | PF | NP | DD |
|-----|--:|---:|---:|---:|---:|
| Family (risk 1%, cap 0.5 lot) | **17** | 29.4% | 7.83 | +$105 762 | **54.9%** |
| Always-long 0.5 lot (control) | 1 | — | — | **+$127 643** | — |

Soft gates: n≥40 **fail** (thin 17) · PF≥1.2 pass · NP>0 pass · DD≤15% **fail** · **beat always-long fail**.

Falsifier confirmed: pullback-long under-captures the 2021–25 drift vs sitting 0.5 lot. High PF is a few runners, not a passer.

**Do not** retune 5/5 / weekly 20 / 0.25 ATR, peek holdout, or attach GOLD_SCALP. Kill `KILL_XAU_H4_PULLBACK_WEEKLY_LONG_ONLY` if this line is reopened. Next family K_prior=12.
