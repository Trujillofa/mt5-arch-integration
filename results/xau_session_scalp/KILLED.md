# XAU / index kill inventory — new-thesis hunting

| Field | Value |
|-------|--------|
| **Date** | 2026-09-10 |
| **Role** | Persist every killed / ineligible thesis on `research/xau-session-scalp` so a later hunt cannot repeat them |
| **xau_loop** | **untouched** — `results/xau_loop_status.md` stays `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` · **promote=no** · **live_go=false** |
| **Authority** | This campaign's locks/NOTE files · [BACKTEST-RECORD.md](../../docs/research/BACKTEST-RECORD.md) · [MATH-MODELS-ROADMAP.md](../../docs/research/MATH-MODELS-ROADMAP.md) · `results/xau_loop_status.md` · `results/xau_charter_disposition_registry.jsonl` |

Not a new screen. Not a reopen. Loop disposition is **not** changed by this file.

A **new** thesis needs a new `family_id`, freeze-before-peek, a different horizon/structure, and a costed beat-the-baseline. Do **not** retune, rename, invert, subset, or stack the rows below.

---

## This campaign (2026-09-08 … 2026-09-09)

| family_id / name | Why dead | New thesis must not repeat |
|------------------|----------|----------------------------|
| `xau_london_defined_r_be_flat_v1` + `GoldSessionScalp` M5 (supersedes `xau_london_orb_overlap_vwap_ema_flat`) | Cost-killed session-OR scalp. Official primary `tpr1_be0_ts6` select n=230 WR 47.8% PF 0.83, `eligible=false`. 0/16 frozen cells eligible. Tight `0.35R` is the **80% WR trap** (WR 69.6% / PF 0.60 — never reached 80%). Median hold ~2 M5 bars: SL/TP race, not a time leak. | Do not retune tp_r / BE / time-stop / OR / EMA / windows. Do not chase **80% WR + PF≥1 on sub-15m XAU**. Do not attach buffer 8 as a live host. Do not zero `slippage_points`. Do not freeze another London/NY/COMEX ORB or far-limit overlay for that dual-goal. |
| `ny_cash_orb_vwap_ema_flat` on gold (unmodified US-index rules, flatten **15:45 ET**) | FP M5 develop PF **1.01** (n=191); Vantage M15 develop PF 1.11. Hours-long trend hold riding 2024–26 gold drift (median MAE ~15 vs scalp ~2). Event clock is still US **cash** 09:30 — gold does not have that print. Holdout melt-up is eval-only. | Do not relabel 15:45 flatten PF~1 as a scalp. Do not copy `UsIndexSessionScalp` onto XAU. Do not promote a multi-hour gold drift ride as this overlay. |
| `xau_h1_bb_rsi_garch11_invvol_size_v1` | Inverse-vol GARCH(1,1) on **frozen** `bb_rsi` `strategy_params.json` (lots only). Develop: GARCH PF 1.42 / +1.08k **lost to ATR-lot** PF 1.67 / +1.19k (n=42, thin). Host replay matched the shipped window. | Do not hunt GARCH knobs on this host. Do not treat GARCH as a +1/−1 signal. Do not stack vol-targeting on any SCREEN_FAIL / null-killed family. `bb_rsi` stays null-killed as a **search** family. |
| `exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1` | Daily rolling OLS on yfinance DXY + nominal US10Y; next-bar sign-follow. Develop PF **0.99** / −186 vs always-long PF **2.02** / +15.7k. Robust w120 not used to pick (also ~0.99). | Do not retune 60/120 after peek. Do not add VIX as a third factor on this tape. Do not reopen `exog_london_fx_cosign_xau_follow_flat`. Sign-follow of a residual is not a gold edge on a bull tape. |
| `exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1` | Same β shape on FRED DFII10 + DTWEXBGS (real yield + broad dollar). Develop PF **0.80** / −8.4k vs always-long PF **1.78** / +22.4k (n=201). Holdout β looking better is **not** a continue. | Do not retune after seeing holdout. Do not swap unused FRED stores (DGS10 / T10YIE / DFII5) into the same sign-follow. Real-yield β still lost to drift. |
| `exog_dfii10_regime_long_or_flat_v1` | Long gold iff DFII10 falling over frozen 20d, else flat; never short. Develop PF 1.48 / **+6.0k loses to always-long +25.6k**. Holdout-once PF 0.83 / −1.8k. Flattening on rising real yields missed the up-move. | Do not start a fifth overlay. Do not retune lookback / percentile / SL from the holdout peek. PF≥1 without beating the drift baseline is not a passer. |
| Combining failed edges | Sibling hunt leftover (unused FRED DGS10/T10YIE/DFII5, H1 DXY/10Y/VIX, QQQ, NFP/CPI/FOMC) plus stacking killed overlays is **not** an independent costed host. MATH-MODELS: do not drop a model on a dead screen. | Do not AND/OR killed families, splice leftover macro onto a killed host, or treat “unused series exist” as a new thesis. New `family_id` + freeze-before-peek or nothing. |
| always-long as a deploy | Always-long is the **vs-drift baseline**, not a strategy. It won because 2024–26 gold drifted up. Regime/β books that lose to it are dead; the baseline itself is not a live-go. | Do not ship buy-and-hold gold as a research passer. Do not invert a losing overlay into always-long and call it edge. Score must beat the declared drift/control **and** clear the family gates. |
| JForex / ismailfer `dukascopy-api-websocket` as tick source | Java JForex SDK proxy (last commit 2022). Demo/live **username+password**, bars-only REST, live book websocket (default instruments have **no XAU**), and it **places orders**. | Do not stand it up. Do not use it for the XAU L1 slip job. Keep any later ticks from the existing public `.bi5` fetcher. No JForex login, no FreeServ key. |
| Dukascopy fill-vs-quote **−19.5** as a cost | Bounded `.bi5` audit: median fill-vs-Dukascopy-touch **−19.5 pt** (n=45). Cross-venue basis (fills *better* than Dukascopy), not request→fill. `usable_as_cost_assumption=false`. Right tail +367 pt. Official `xau_research_costs.json` stays slip **0 UNMEASURED**. | Do not write −19.5 into the cost book (that gifts H1 PF). Do not invent slip from half-spread. Do not treat this sample as Standard-STP friction. Label fill-vs-quote vs request→fill. |

Official campaign artifacts: `defined_r_v1_{lock,pareto,primary}.json` · `results/xau_{garch_size,exog_beta,exog_beta_realyield,exog_regime}/` · `results/xau_research_slip.json`. Tick dump `results/xau_slip_ticks/` stays **gitignored**.

---

## Prior XAU / index (this worktree; do not change loop disposition)

| family_id / name | Why dead | New thesis must not repeat |
|------------------|----------|----------------------------|
| `bb_rsi` | `KILL_BB_RSI_LINE`. Max PF (n≥20) **2.242** but `p_max_pf=0.854`, `p_n_passers=0.707` — search measured itself. | Do not retune BB/RSI hours/SL/TP. Do not treat a high in-sample max PF as edge. GARCH-on-frozen-`bb_rsi` (above) also failed and does **not** reopen the search family. |
| `donchian_turtle` | `KILL_DONCHIAN_LINE`. Max PF **1.995**; `p_max_pf=0.195`, `p_n_passers=0.293`. Multi-year autopsy: sign-stable including 2023 is still **promote=no**. | Do not revive turtle / Donchian / ATR-trail as a sealed host. ATR-trail collapsed 2023 in the same autopsy. |
| Walk-forward / holdout collapse (frozen catalog) | Train PF **1.837** → OOS PF **0.588** (n=7). Peeked 2026 windows. Skeptic **promote=no**. | Do not relabel IS / peeked years as OOS. Do not re-mine `2026_to_peek`. A refit is not a virgin eval. |
| `prior_day_high_break` | `KILL_PRIOR_DAY_HIGH_BREAK`. Real max PF (n≥20) **1.077**; `p_max_pf=0.463`; soft passers **0** (null can match/beat). | Do not flip Asia-box fades into prior-day breakout continuation — same neighborhood, already closed. |
| `tod_london_ny_flat` | `PROTOCOL_NULL_INVALID` / exploratory SCREEN_FAIL. `day_block_shuffle` invalid for session-hour rules. Charter restored byte-for-byte; r1 **not** burned. | Do not reuse an invalid null as a pass. Do not seed-shop. Next TOD-like rule needs a valid within-day rotate **and** a new `family_id`. |
| `server_hour_window_flat` | SCREEN_FAIL, zero primary passers (develop PF **0.851**, NP −5.1k, DD 59%, n=1114). Null not run (`p_n_passers=1`). | Do not retune the hour window. Do not treat “server hour 13 ≈ London–NY” as proven. |
| `early_server_range_break_flat` | SCREEN_FAIL. Best n≥20: PF **0.783**, NP −4.1k, DD 48%, n=542. | Do not retune range hours / SL/TP. Continuation of early-range breaks is closed. |
| `day_open_reclaim_flat` | SCREEN_FAIL. Best n≥20: PF **1.035**, NP +1.3k, DD 31%, n=835 — soft needs PF≥1.1 and fails. | Do not peek holdout to clear the 1.1 PF soft gate. Do not loosen DD/PF pins. |
| `joint_london_open_cosign_fade_flat` | v4 SCREEN_FAIL. Joint PF **0.865**, NP −10.1k, DD 43%, n=1821. All three per-symbol soft fail. | Do not retune joint cosign knobs. Do not revive v1–v3 (SUPERSEDED). Fade of a London-open basket is closed. |
| `exog_london_fx_cosign_xau_follow_flat` | SCREEN_FAIL (v4). Pooled PF **0.903**, soft 0. Best recent XAU pooled PF — still fail. Stratified gate did its job. | Do not retune T* / threshold / occupancy. Do not report pooled-only. A sequel needs a **new** `family_id` (MATH-MODELS tv-β shape), not a rename of this SHA. |
| `asia_box_london_sweep_fade_flat` | SCREEN_FAIL. n=670, PF **0.553**, NP −8.1k, DD 82%. Sweep-and-reclaim *event* is real; the *fade* loses. | Do not retune hours/SL/TP/occupancy. Do not invert to breakout-continuation (prior-day / early-range neighborhood). |
| `multi_day_variance_expansion_flat` | SCREEN_FAIL. n=206, PF **0.921**, NP −506, DD 14.9%. Fade after 5d/20d expansion pays spread. | Do not retune 5/20/1.5 / flatten hour. Do not ride the expansion on the same events. |
| `htf_fib_offline_replay_v1` / `ForexHtfPivotsFib` | Observe + **frictionless** lock (`slippage_points=0`, no spread column). Not a sealed money screen. Not a host. | Do not treat frictionless Fib PnL as a passer. Do not attach GARCH/LGBM to Fib until a charter + costed book exists. Do not re-derive pivots (lookahead). |
| US-index session `ny_cash_orb_*` / `us_index_session_autoresearch` **v1–v8** | 1%/20% goal **archived**. v8: 0/32. v4 already skipped HMM. Overlay `UsIndexSessionScalp` observe-only. | Do not retune v1–v8, raise lots, or cut slip to manufacture 1%/20%. Do not stack GARCH/HMM/LGBM/RL on this screen. Do not reopen news-drift / M1 / US500. |

Standing dead-line count at last XAU loop write: **11** scored families (`xau_loop_status.md` 2026-08-21). This campaign's overlays are **additional** and do **not** edit that file.

### Related closed lane on this worktree (not XAU)

| family_id / name | Why dead | New thesis must not repeat |
|------------------|----------|----------------------------|
| `eurusd_ny_scalp_develop_v1` + `eurusd_ny_mr_limit_fill_v1` | Screen **0/192**. MR paper gate **FAIL** (median edge 7 vs median RT 11; fill_rate 0.985 invalid as a limit). Intraday own-price class falsified under ~22 pt RT. | Do not subset the 7,819 MR signals. Do not invert ANTI trend_continuation. Mean-vs-median-only paper gates are forbidden; `fill_rate ≳ 0.70` is a validity fail. |

---

## What a new thesis is allowed to be

Change **horizon / structure / risk module**, not a closed book.

- Daily/weekly theses where ~$25 gold RT (or ~22 pt FX) is a small fraction of the move.
- New `family_id` + freeze-before-peek; holdout `2026-01-01` never for selection.
- Replay `results/xau_research_costs.json` (slip **0 UNMEASURED**) or a **new** lane lock — never the frictionless Fib lock, never invented −19.5.
- Beat a declared control **after costs** on develop only (constant/ATR lot, always-long/drift, or a frozen link arm).
- Plug-in models (GARCH / tv-β / OU) attach to a **new or still-open** host — not to any row above.

Do **not** write `strategy_params.json` or edit `results/xau_loop_status.md` from a killed-track reopen.
