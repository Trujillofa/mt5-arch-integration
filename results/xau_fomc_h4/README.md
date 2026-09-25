# Vantage XAUUSD H1 dump for `xau_fomc_h4_long_only_v1`

**Source:** MT5 MCP `get_chart_history` on Vantage `XAUUSD` H1 (prefix `~/.mt5-vantage`), 2026-09-18.

| Field | Value |
|-------|--------|
| File | `xauusd_h1_2018_2025.csv` |
| Bars | 45 863 |
| First true H1 | **2018-04-02 01:00** |
| Last | 2025-12-31 23:00 |
| 2018-01 … 2018-03 | **Not H1** on this terminal (D1 only) — Jan/Mar 2018 FOMC unusable |

Spread missing on 4 233 bars (mostly 2018); median of present = 16 pt. Impute median at screen time, do not invent 0.

Do not overwrite `xauusd_data.csv`. Holdout still `2026-01-01`.
