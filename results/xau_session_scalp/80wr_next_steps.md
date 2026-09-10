# Defined-R v1 recommendation — 80% WR + PF>=1 (not an implementation)

**Date:** 2026-09-09  
**Family:** `xau_london_defined_r_be_flat_v1` (supersedes `xau_london_orb_overlap_vwap_ema_flat`)  
**Official artifacts only:** `results/xau_session_scalp/defined_r_v1_lock.json`, `defined_r_v1_pareto.json`, `defined_r_v1_primary.json`  
**Primary book:** `tpr1_be0_ts6`  
**USER GOAL:** 80% win rate AND PF>=1 after gold costs  
**Standing:** promote=no · live_go=false · **goal closed on this event class**  
**Branch note:** `xau-scalp-80wr-next` is this memo’s name. Work lives on `research/xau-session-scalp`. No such git branch.

This is a recommendation. Do not rerun the grid, recompute official metrics, write `strategy_params.json`, edit `results/xau_loop_status.md`, or pass `--live`.

The **first** defined-R background grid hung on a slow OR-width lookup and was killed after ~2 minutes. It did **not** write official metrics (`hung_job_wrote_metrics=false`). Ignore any partial/temp output from that job. The **later optimized run** is the only official record.

---

## 1. What is already true about `tpr1_be0_ts6`

Lock (`defined_r_v1_lock.json`): frozen **before** metrics (`frozen_before_metrics=true`). Grid = `tp_r ∈ {0.35, 0.5, 0.7, 1.0}` × `be_r ∈ {0, 0.4}` × `time_stop_bars ∈ {0, 6}` (cardinality 16). Score window is **select only** (`utc_date ≤ 2025-10-31`). Eligible = select n≥40 and PF≥1.0 and payoff≥0.22 and not degenerate WR. Rank among eligible = max WR. If none eligible: honest book = max select PF among n≥30; **do not pick by confirm or holdout**.

Primary was picked for that fallback, not as a passer:

| Field | Value |
|-------|--------|
| id | `tpr1_be0_ts6` |
| params | SL 1.0 ATR, TP 1.0R, BE off, 6-bar time-stop |
| pick_reason | `no_eligible_max_select_pf_n30` |
| eligible | **false** |
| promote / live_go | **no / false** |
| costs | point 0.01, contract 100, 1 lot, commission 0, **slippage_points=10** (unmeasured, frozen), spread cap 40 |
| tape | FP `XAUUSD.r` M5.hc, sha256 `f98e19f1…dcccd0`, 100190 bars, 2025-04-03 → 2026-09-01 UTC |

Select (used to pick):

| Slice | n | WR | PF | Net (1 lot) | payoff | 0.5% of $10k |
|-------|--:|---:|---:|------------:|-------:|-------------:|
| Select ≤2025-10-31 | **230** | **47.8%** | **0.832** | **−5 886** | 0.91 | −1 400 |

Exits on select: TP 105 / SL 109 / time-stop 16. Median MAE 2.15 vs MFE 2.00. Median risk lots 0.19. Every trade has a hard stop.

Confirm / develop / holdout were evaluated **once** after the pick and were **not** used to choose the cell:

| Slice | n | WR | PF | Net (1 lot) |
|-------|--:|---:|---:|------------:|
| Confirm Nov–Dec 2025 | 40 | 45.0% | 0.72 | −2 351 |
| Develop `< 2026-01-01` | 270 | 47.4% | 0.81 | −8 237 |
| Holdout ≥2026-01-01 (eval only) | 226 | 44.2% | 0.78 | −14 126 |

`wr80_verdict` on the primary (and Pareto):

- `hit_80_and_pf1_on_select` = **false**
- `select_n` = 230, `select_wr` = 0.478, `select_pf` = 0.832
- `if_missed`: *"80% WR and PF>=1 after gold costs are incompatible on this select tape under the frozen 16-cell defined-R grid. Tight TP cells raise WR but fail payoff/PF; wider TP keeps the 2-bar SL/TP race."*

---

## 2. Why 80% WR + PF>=1 missed on this family

The joint gate was pressure-tested **on select** under a freeze-before-peek 16-cell grid. Result: **0 / 16 eligible**.

Highest WR on the frozen grid (WR-trap, not a passer):

| Cell | n | WR | PF | Net $ | payoff |
|------|--:|---:|---:|------:|-------:|
| `tpr0.35_be0_ts0` | 168 | **69.6%** | **0.60** | −7 357 | 0.26 |
| `tpr0.35_be0_ts6` | 168 | 69.6% | 0.60 | −7 357 | 0.26 |

Lock grill (`wr80_grill`): at WR=80%, need `tp_r ≥ (c/S + 0.20) / 0.80`. With S≈$2.6 ATR and c≈$25, that is **`tp_r ≥ 0.37`**. The locked 0.35R cell is the WR-trap: highest WR and worst PF among no-BE cells. It still **never reached 80%** (10pp short). Tighter TP was **not** searched after peek because it deepens the trap (payoff 0.26 already; one loser wipes ~4 winners).

Wider TP (the honest book) keeps the 2-bar SL/TP race: primary WR 47.8% PF 0.83. No-BE 0.5R/0.7R cells sit in between (WR 58–67%, PF 0.73–0.78) and are also ineligible.

BE at 0.4R **destroys** WR (6–11%, PF ≤ 0.11): gold M5 often tags 0.4R then mean-reverts through entry; those scratches are losses after costs. 0-vs-6 time-stop was already in the lock and did not create an eligible cell.

This is microstructure, not an exit bug. Prior ATR-book autopsy (develop, n=381): median hold **2 M5 bars**; SL 215 / TP 164; London and NY equally negative; flatten almost never fires. MAE≈MFE on the defined-R book is the same race.

Horizon/cost knobs cannot manufacture the pair as a still-scalp honest gold book:

- Frozen 10 pt/side slip (~$20 RT) plus spread is the official book. Zeroing unmeasured slip is refused by `refuse_frictionless` and would still leave the trap cell at WR 69.6% (not 80%).
- Limit fills are the same cheat plus a different (pullback) fill model.
- M15 is already falsified for this overlay: Vantage M15 transfer of `london30_both_windows` is develop WR 45.5% PF 0.83; Vantage M15 spreads are wider (~18 pt) than FP M5 (~6 pt).
- 15:45 ET flatten is the **index-on-gold baseline** (FP M5 develop n=191 WR 52.4% PF 1.01; Vantage M15 WR 50.0% PF 1.11), a multi-hour trend hold (median MAE ~15 vs scalp ~2), not a scalp win for this overlay.

A new London/NY/COMEX session-OR or far-limit overlay aimed at the same dual-goal is the same **intraday own-price** class already falsified (`docs/research/BACKTEST-RECORD.md`). Naming COMEX 08:20 as able to clear the pair would invent edge.

---

## 3. Ranked next steps

No remaining path is `viable_for_80wr_and_pf1`. The 80% WR scalp goal is **closed on this event class**. Ranked honest close-out plus non-80% research that is still allowed:

1. **Close-out — EXECUTED 2026-09-09.** Disposition in `STATUS.md`. Official artifacts left intact. Docs/HOWTO/indicator stamped CLOSED / observe-only. Primary stays `tpr1_be0_ts6`, `eligible=false`, `promote=no`, `live_go=false`. Do not touch `results/xau_loop_status.md` (still `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`) or `strategy_params.json`.
2. **If XAU research continues, change horizon/structure — freeze-before-peek a new `family_id`.** Daily/weekly theses where ~$25 RT is a small fraction of the move. Own event, falsifier, small grid, `select_end ≤ 2025-10-31`. Holdout `2026-01-01` never for selection. **Do not** write a freeze memo for a new London/NY/COMEX ORB or limit-fill overlay aimed at 80% WR + PF>=1.
3. **Optional MATH-MODELS item — GARCH size probe RUN 2026-09-09 (`results/xau_garch_size/`, **kill**).** GARCH/EGARCH as a **risk filter** (sizing/stops, not +1/−1) on a new or still-open host. Charter and costs frozen first. Beat constant-lot / ATR-lot after Standard STP on develop only. Not eligible: any SCREEN_FAIL `family_id`.
4. **Optional MATH-MODELS item — DXY+US10Y daily β RUN 2026-09-09 (`results/xau_exog_beta/`, **kill**).** new exogenous time-varying-β (Kalman/rolling β) or later OU/coint spread at H1/daily. New `family_id`. Do **not** retune closed `exog_london_fx_cosign_xau_follow_flat` v4 (pooled PF 0.903) or `joint_london_open_cosign_fade_flat`.
5. **GoldSessionScalp stays research-only.** Wine compile / chart attach is observe-only. It is the only gold-scalp overlay in-repo; "only" is not edge. Not a live-go.
6. **Optional MATH-MODELS item — FRED real-yield daily β sign-follow RUN 2026-09-09 (`results/xau_exog_beta_realyield/`, **kill**).** Family `exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1`. Do **not** reopen.
7. **Real-yield REGIME long-or-flat RUN 2026-09-09 (`results/xau_exog_regime/`, **kill**).** Family `exog_dfii10_regime_long_or_flat_v1`. Develop PF 1.48 / +6.0k loses to always-long +25.6k. Holdout-once only. Slip **GAP**. Research stays idle. **Do not start a fifth overlay.**

---

## 4. Hard do-not list

- Do not rerun the optimized 16-cell defined-R grid.
- Do not recompute official metrics.
- Do not treat the hung first job as metrics; ignore its partial/temp output.
- Do not retune the peeked 16 cells (`tp_r` / BE / time-stop / OR-width / EMA / windows) on `xau_london_defined_r_be_flat_v1` after peek.
- Do not pick on confirm or holdout; do not search holdout 2026-01-01.
- Do not `--live`.
- Do not write `strategy_params.json`.
- Do not edit `results/xau_loop_status.md`.
- Do not treat WR-trap cells as passers; do not search tighter TP than 0.35R after peek.
- Do not set `slippage_points=0` or call limits a zero-slip fill.
- Do not claim M5 + Vantage-STP jointly (no Vantage M5 develop tape).
- Do not relabel 15:45 ET flatten PF~1 as this scalp.
- Do not switch this overlay to M15 to manufacture the pair.
- Do not freeze another M5 session-scalp event/fill for the 80% WR dual-goal.
- Do not reopen closed XAU charter families: `asia_box`, `day_open`, `prior_day_high`, `tod`, `server_hour`, `early_range`, `joint_fx`, `exog_fx`, `multi_day`, `bb_rsi`, Donchian.
- Do not reopen `exog_dfii10_regime_long_or_flat_v1`, `exog_dfii10_dtwex_daily_tvbeta_xau_follow_flat_v1`, `exog_dxy_us10y_daily_tvbeta_xau_follow_flat_v1`, or `xau_h1_bb_rsi_garch11_invvol_size_v1`.
- Do not invent slip or rewrite `xau_research_costs.json` from the GAP note.

