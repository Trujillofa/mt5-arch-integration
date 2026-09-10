# DFII10 real-yield regime — long or flat (KILL)

| Field | Value |
|-------|--------|
| family_id | `exog_dfii10_regime_long_or_flat_v1` |
| kind | new research family (not a reopen of β sign-follow) |
| disposition | **kill** on develop vs always-long |
| promote / live_go | **no / false** |
| xau_loop | **untouched** (`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`) |
| frozen_before_metrics | true (`lock.json`) |
| costs | `xau_research_costs.json` slip **0 UNMEASURED** |
| slip hunt | `results/xau_research_slip.json` **GAP** — official book not rewritten |

Thesis: gold is a real-yield **asset**. Stay **long or flat**. Never short
(the β-follow books died on shorts). Primary rule uses **only** DFII10.
No DTWEX / DXY / VIX. No daily OLS residual.

## Lock (frozen first)

- Driver: FRED `DFII10` cache, as-of merge (last print with date ≤ gold UTC date).
- Primary: long iff `DFII10_asof[t] < DFII10_asof[t-20]`, else flat.
- Robustness (logged, **not used to pick**): long iff DFII10 < 40th percentile of prior 252 days.
- Timing: daily gold from `xauusd_data.csv`; enter/exit **next daily open** after the regime is knowable; hold while on; flatten on flip. No catastrophe SL on the official book.
- Size: 0.10 lot (same as prior β books).
- Select: `utc_date < 2026-01-01`. Holdout evaluate **once**.
- n floor: **regime-on days ≥ 30** (met: 550).
- Score: develop PF ≥ 1 **and** net > always-long net. Always-long is one continuous long through the window (PF on n=1 is a 99 sentinel; binding vs-drift test is **net**).

## Develop (`utc_date < 2026-01-01`)

| Book | n | on-days | WR | PF | Net (0.10 lot) | max DD% |
|------|--:|--------:|---:|---:|---------------:|--------:|
| regime_falling_20d | 56 | 550 | 51.8% | **1.482** | **+6 041** | 27.5 |
| always_long_continuous | 1 | 1096 | 100% | 99* | **+25 581** | 0† |
| robust_pct40_not_pick | 22 | 236 | 40.9% | 3.86 | +9 638 | 20.7 |

\* Always-long is one RT; PF is not the vs-drift test.  
† Intra-hold drawdown is not marked on a single completed trade.

**Verdict: kill.** PF ≥ 1, n floor cleared, but net **does not beat** always-long (+6.0k vs +25.6k). The gate did not earn its keep vs the drift. Flattening when real yields were rising missed a large gold up-move.

Robustness row is **not** a salvage path. It also loses on net vs always-long.

## Holdout (evaluate once — not used to pick)

| Book | n | on-days | WR | PF | Net | max DD% |
|------|--:|--------:|---:|---:|----:|--------:|
| regime_falling_20d | 11 | 58 | 63.6% | 0.828 | −1 837 | 51.4 |
| always_long_continuous | 1 | 155 | 100% | 99* | +140 | 0† |

Holdout would also fail PF < 1. Do **not** retune lookback / percentile / SL from this peek.

## After this book

Research stays **idle**. Do **not** start a fifth overlay. Do **not** reopen
GoldSessionScalp, 16-cell M5, GARCH-on-bb_rsi, DXY/10Y β, or
`exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1`.

Still **research-only / promote=no**. No live orders. `strategy_params.json`
was not `--save`d. `xau_loop_status.md` was not edited.
