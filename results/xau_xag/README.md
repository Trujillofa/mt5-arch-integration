# Vantage XAGUSD H1 dump for `xau_xag_logspread_ou_fade_v1`

**Source:** MT5 MCP `get_chart_history` on Vantage `XAGUSD` H1, 2026-09-19.

| Field | Value |
|-------|--------|
| File | `xagusd_h1_2018_2025.csv` |
| First true H1 | **2018-04-02 01:00** |
| Last | 2025-12-31 23:00 |
| Join | Inner join on server date with `results/xau_fomc_h4/xauusd_h1_2018_2025.csv` |

Spread missing early; median-impute at screen. Holdout still `2026-01-01`.
