# XAU session scalp — track status

| Field | Value |
|-------|--------|
| **disposition** | **CLOSED** |
| **observe** | **only** — chart overlay / research artifact. Not a live entry host. |
| **promote** | **no** |
| **live_go** | **false** |
| **goal_80wr_and_pf1** | **closed on this event class** (M5 London/NY session-OR scalp) |
| family_id | `xau_london_defined_r_be_flat_v1` |
| primary | `tpr1_be0_ts6` (`eligible=false`) |
| official_record | `defined_r_v1_lock.json` · `defined_r_v1_pareto.json` · `defined_r_v1_primary.json` |
| kill_inventory | **`KILLED.md`** — this campaign + prior XAU/index SCREEN_FAIL / promote=no (hunting lock) |
| closed_at | 2026-09-09 |
| xau_loop | **untouched** (`results/xau_loop_status.md` still `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`) |

This file exists so a later agent cannot treat M5 gold scalp as an open
tuning problem. Metrics JSON under this directory are **terminal records**.
Do not delete, rewrite, or “clean up” them.

Hunt inventory (every killed / ineligible thesis on this worktree):
`results/xau_session_scalp/KILLED.md`. Do not change `xau_loop_status.md`.

## Hard forbids (next agent)

- Do **not** retune `xau_london_defined_r_be_flat_v1` (tp_r / BE / time-stop / OR-width / EMA / windows).
- Do **not** add cells to the frozen 16-cell grid or rerun it for official metrics.
- Do **not** peek holdout `2026-01-01` to salvage PF.
- Do **not** chase **80% WR on sub-15m XAU**.
- Do **not** swap this overlay onto indices (`UsIndexSessionScalp` is a different event).
- Do **not** attach `GoldSessionScalp` as a live signal / order host.
- Do **not** write `strategy_params.json` or edit `results/xau_loop_status.md` from this track.
- Do **not** set `slippage_points=0` to manufacture a passer.

## If XAU research continues

Change horizon/structure. New `family_id` + freeze-before-peek. See
`docs/research/MATH-MODELS-ROADMAP.md` and `results/xau_session_scalp/80wr_next_steps.md`.
GARCH / exogenous-β were **not** started from this close-out.

Memo: `80wr_next_steps.md` (`xau-scalp-80wr-next` is this memo’s name, not a git branch).

## GARCH size probe (started 2026-09-09)

See `results/xau_garch_size/` (`xau_h1_bb_rsi_garch11_invvol_size_v1`).
H1 host `strategy_params.json` only. **Verdict: kill** (did not beat ATR-lot
on develop). This does **not** reopen M5 gold scalp.

## Exogenous β probe (started 2026-09-09)

See `results/xau_exog_beta/` (`exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1`).
Drivers: crypto-agent yfinance DXY + US10Y daily snapshots (not TIPS).
**Verdict: kill** vs always-long on the same dates. Does not reopen M5 scalp or GARCH.

## Real-yield β probe (started 2026-09-09)

New family `exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1` after a FRED panel
(`results/xau_exog_beta/data/fred/`, `env: FRED_API_KEY`). Artifacts:
`results/xau_exog_beta_realyield/`. **Verdict: kill** vs always-long on develop.
Does not reopen DXY β, GARCH, or M5 scalp.

## Real-yield REGIME gate (started 2026-09-09)

New family `exog_dfii10_regime_long_or_flat_v1` — long gold iff DFII10 is
falling over a frozen 20-day lookback, else flat. Never short. Artifacts:
`results/xau_exog_regime/` (`lock.json`, `develop.json`, `holdout.json`, `NOTE.md`).
**Verdict: kill** — develop PF 1.48 but net +6.0k loses to always-long +25.6k.
Holdout-once PF 0.83 / −1.8k (evaluate only). Slip hunt is a **GAP**
(`results/xau_research_slip.json`); official costs stay slip 0 UNMEASURED.
Does not reopen β sign-follow, DXY β, GARCH, or M5 scalp. **No fifth overlay.**
Research stays idle / RESEARCH_ONLY / promote=no.

