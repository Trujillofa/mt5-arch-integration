# `eur_gbp_logspread_ou_fade_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** (2026 in package unused) |
| **tape** | Phase 0 EUR∩GBP daily 2021-09-07→2025-12-31 (1121 days) |

Off-gold. Expanding β min 252, \|z\|>2, exit 0 or 5d. 0 knobs.

| Arm | n | WR | PF | NP | DD |
|-----|--:|---:|---:|---:|---:|
| EUR–GBP OU fade | **29** | 62.1% | 2.01 | +$519 | 1.60% |
| Always-long EUR 0.10 (report) | 1 | — | — | +$1.8k | — |

PF, NP, DD pass. **n=29 < 40** fails. Thin n is a fail, not a waiver. Do not retune 252/2/5 to farm trades.
