# xau_gold_session_study — develop screen · SCREEN_FAIL

Offline, research only. Holdout (2026-01-01+) **untouched**. promote=no · live_go=false.

- **Script:** `scripts/xau_gold_session_study.py` (default `--window develop`)
- **Data:** Vantage XAUUSD M1 via official MT5 MCP `get_chart_history` (`scripts/fetch_m1_official_mcp.py`), 968,301 bars 2024-01-02 → 2026-09-24 server time, sha256 `d457e11e…5f75`, 2,669 bars without a spread value (carried forward). Develop window: 500 trading days, 2024-01-02 → 2025-12-31.
- **Costs:** per-bar `MqlRates.spread`, which is the *minimum* tick spread in the bar (checked 120/120 minutes against ticks); slippage sensitivity +0/5/10/20 pt.

## 1. Timing of the day's extreme (London open → 17:00 NY)

Null: block sign flips (30 min, random phase) around the sample drift, 500 sims, empirical p. Calibrated on 40 synthetic random walks (5.0% of claim p-values < 0.05).

| test | real | null | p |
|---|---|---|---|
| claim 15:30–16:30 UTC, all days (primary) | 12.0% | 9.8% | 0.062 |
| same, summer | 11.0% | 9.5% | 0.224 |
| same, winter | 14.7% | 11.0% | 0.060 |
| best 2 h window, UTC, family-wise | +3.8 pp | — | 0.17 |

The best window moves −1 h (UTC) / −2 h (London, NY) between summer and winter, so no clock holds it. The only faint lead is winter 14:30–16:30 UTC (fw p 0.07) — not significant, and found by search.

## 2. London range sweep + reclaim → VWAP (avg R per trade, no BE)

| ref | side | n | avgR | t | at +10 pt |
|---|---|---|---|---|---|
| LDN_AM | long@low | 214 | +0.06 | 0.44 | +0.01 |
| LDN_AM | short@high | 220 | −0.20 | −1.80 | −0.25 |
| LDN_FULL | long@low | 63 | −0.36 | −2.02 | −0.41 |
| LDN_FULL | short@high | 91 | −0.39 | −2.28 | −0.45 |

## 3. Fade ≥1 ATR(M15) from London VWAP at fixed times

All 7 anchors negative: −0.06R (17:00 UTC) to −0.29R (15:00 London), n 291–299 each.

## Disposition

**SCREEN_FAIL** for all three idea groups. Do not run the holdout on them: they failed develop, and ~180 holdout days cannot resolve a ~2 pp timing effect. Do not retune claim window, reclaim minutes, ATR multiple, stop lookback or BE rules.
