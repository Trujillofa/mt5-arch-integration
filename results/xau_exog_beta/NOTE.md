# XAU exogenous β — DXY + US10Y daily (kill)

| Field | Value |
|-------|--------|
| Date | 2026-09-09 |
| Family | `exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1` |
| Lock | `lock.json` — **frozen before** metrics |
| **Verdict** | **kill** |
| promote / live_go | **no / false** |
| Not a reopen | `exog_london_fx_cosign_xau_follow_flat` |

Rolling OLS of daily gold log-returns on DXY and US 10Y, next-bar sign follow,
5-day occupancy, 1.5 ATR stop, 0.10 lot. Horizon is **D1**, not M5.

## Data inventory (other repos, read-only hunt)

| Repo / place | Series | TF | Range | Used? |
|--------------|--------|----|-------|-------|
| **TRADING/crypto-agent** `data/tradfi/` | DXY (`DX-Y.NYB`) | D1, H1 | 2024-01 → 2026-06 | **Yes (D1)** |
| same | US10Y (`^TNX`) | D1, H1 | 2024-01 → 2026-06 | **Yes (D1)** |
| same | VIX (`^VIX`) | D1, H1 | 2024-01 → 2026-06 | Copied, **not in frozen rule** |
| same | QQQ equity_risk | D1, H1 | 2024-01 → 2026-06 | No (not a gold β driver) |
| this worktree Phase 0 | XAU/EUR/GBP H1 | H1 | packaged | Fallback only; not primary |
| this worktree `xauusd_data.csv` | XAUUSD | H1/M15 | 2021-09 → 2026-08 | **Gold host** (H1→D1) |
| ctrader-trading-agent `data/merged_live_pairs_2022_2026.csv` | EURUSD…USDJPY | H1 | 2022–2026 | Not used (FX, not DXY) |
| ctrader `/tmp/dukascopy-h1` | — | — | missing | — |
| vibe-investing | FRED *code* only | — | no yield/DXY CSV | Gap |
| manual-trading-agent | `zonas DXY.tpl` | — | template, no series | — |
| trading-evidence / okx-outcomes | — | — | no TradFi β tape | — |
| Wine MT5 caches | USDJPY, XAUUSD | various | broker history | Not copied (not DXY/TIPS) |
| **TIPS / US real yields** | — | — | **nowhere on disk** | Gap |
| UUP / DX=F | — | — | not stored (crypto-agent picked DX-Y.NYB) | — |

crypto-agent files are git-tracked (`!data/tradfi/`), yfinance, no API key, no secrets.
Snapshot copied to `results/xau_exog_beta/data/` (`SOURCE.json`).

This is **DXY + nominal 10Y**, not TIPS/real yields.

## Frozen rule

- Rolling OLS, window **60** (robustness 120 listed, **not used to pick**).
- `pred = β_dxy r_dxy + β_10y r_10y` at day i; trade day **i+1** open if `|pred|≥0.002`.
- Baseline: always-long on the same `|pred|` gate (timing shared; sign forced +1).
- Costs: research book, last H1 spread of the gold UTC date, **slip=0 UNMEASURED**.

## Develop (`utc_date < 2026-01-01`)

| Book | n | WR | PF | Net (0.10 lot) | Max DD |
|------|--:|---:|---:|---------------:|-------:|
| β-follow w60 | 82 | 47.6% | **0.99** | −186 | 48% |
| **always-long same entries** | 79 | 63.3% | **2.02** | +15 680 | 16% |
| robust w120 (not pick) | 74 | 47.3% | 0.99 | −154 | 62% |

n differs slightly (79 vs 82) because long vs short exits change the next free slot.
The β **sign** lost to gold’s 2024–25 drift on the same timing gate.

## Holdout (evaluate once)

| Book | n | WR | PF | Net | Max DD |
|------|--:|---:|---:|----:|-------:|
| β-follow | 23 | 56.5% | 0.81 | −3 235 | 64% |
| always-long | 23 | 43.5% | 1.19 | +3 538 | 36% |

n=23 is below the develop floor. Not used to pick. Same story: long gold beat β sign.

## Kill vs continue

**Kill.** Develop n=82 ≥ 30 but PF 0.99 ≯ always-long 2.02 and PF < 1.0.
Do not retune the 60/120 windows after peek. Do not add VIX as a third factor
after seeing this tape.

GARCH size overlay stays killed. GoldSessionScalp stays observe-only.
No `backtest.py --save`.
