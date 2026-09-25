# `xau_fomc_h4_long_only_v1` — develop screen

| Field | Value |
|-------|--------|
| **verdict** | **SCREEN_FAIL** |
| **promote / live_go** | **no / false** |
| **holdout** | **untouched** (dump ends 2025-12-31) |
| **tape** | MCP Vantage H1 `results/xau_fomc_h4/xauusd_h1_2018_2025.csv` (2018-04-02→2025-12-31, UTC+3 server) |
| **events** | 61 matched · 2 skipped (2018-01-31, 2018-03-21 — no H1) |

Long after scheduled FOMC 14:00 ET, 8 H4 bars, SL 1.5 ATR, 0 knobs.

| Arm | n | WR | PF | NP | DD |
|-----|--:|---:|---:|---:|---:|
| FOMC H4 long | **61** | 44.3% | **1.05** | **+$148** | 6.3% |
| Always-long 0.5 lot | 1 | — | — | **+$149 395** | — |

Fails PF≥1.2 and **beat always-long**. n and DD pass. FOMC windows are not a free lunch vs sitting 2018–25.

Do not retune hold 8 / SL 1.5 / add CPI. Do not peek 2026.
