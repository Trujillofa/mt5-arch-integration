# Offline research backtest record (consolidated)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Standing** | `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` · **promote=no** · **live_go=false** |
| **Purpose** | Single page for “is this already dead?” — not a new search |

This file assembles verified outcomes from screens, nulls, triage, skeptic, and paper gates. It does **not** authorize revival, subsetting, ANTI inversion, or a new screen.

---

## One-line reading

Intraday indicator-on-own-price families, under realistic round-trip friction, have been **falsified as a class** on the data we have. The last cost-side rescue for the only measurable EURUSD edge also **failed on paper**. Next research, if any, must change **horizon / structure**, not retune a closed book.

---

## Structural constraint (why M5 was the hard version)

Friction is roughly **fixed per round trip**; edge scales with hold horizon:

| Setting | Approx move | Friction | Break-even share of move |
|---------|-------------|----------|---------------------------|
| EURUSD M5, ~4h (H50) | ~100 pts | ~22 pts | ~22% |
| EURUSD daily range | ~700 pts | ~22 pts | ~3% |

**Friction composition (do not treat 22 as fully observed):** under `results/eurusd_ny_scalp_lock.json`, round-trip ≈ median spread (~12 pts, measured) + **2 × `slippage_points=5.0`** (= **10 pts assumed** — lock: *"STATED ASSUMPTION, not measured"*). So **~10 of 22 pts are assumed**. Sensitivity: if true slip were 2 pts/side, RT ≈ 16 and mean paper comparisons near 11.5 can flip sign — **median** comparisons and **fill_rate** validity do not; the paper-gate FAIL still stands on those. Slippage calibration from live/deal histograms is deferred until a thesis again lands near break-even.

~**7×** easier bar from horizon alone. Measured EURUSD MR edge **saturates ~11.7 pts by H50** — holding the same signal longer does not clear 22 pts. Lever = thesis whose edge lives where 22 pts is noise — not “hold this MR longer.”

---

## Signal-edge triage (24 measurable families)

Source: `docs/research/SIGNAL-EDGE-TRIAGE.md` · tool `scripts/signal_edge_diagnostic.py` · develop-only.

| Verdict | n | Notes |
|---------|--:|--------|
| DEAD | 17 | |
| COST-BOUND | 1 | EURUSD `mean_reversion` only |
| ANTI | 3 | do **not** invert |
| CLEARS-FRICTION | 2 | US only — see skeptic |
| EMPTY | 1 | |

**EURUSD regression (reproduced):** trend_continuation ANTI (H50 −11.85, t −3.13); mean_reversion COST-BOUND (H50 +11.75, t +4.14); breakout DEAD (H50 −19.18, t −1.68).

**Unmeasurable (finding):** many closed XAU families have no exportable ±1 `signal_fn` (embedded in `simulate()`). Listed in the triage — not omitted.

### CLEARS-FRICTION skeptic (do not promote)

Source: `docs/research/SIGNAL-EDGE-TRIAGE-SKEPTIC.md`

- Across **24** families, \(\mathbb{E}[\max|t|] \approx \sqrt{2\ln 24} \approx 2.52\).
- Observed CLEARS t: **2.44**, **2.24** — **inside the null max**, not above it.
- Short US100 M5 calendar; CLEARS are **2026-driven**; prior exit-grid screens already SCREEN_FAIL.
- Dollar book: `$/MT5 pt = point_size × contract × lots = $0.01` (not $0.02).

Two CLEARS out of 24 at null-expected t = **the correct amount of nothing**.

---

## EURUSD NY-scalp lane (closed)

| Item | Result |
|------|--------|
| Screen `eurusd_ny_scalp_develop_v1` | **0 / 192** develop-eligible; SCREEN_FAIL |
| Null gate | `max_null_best` = **0.075%/day**; no winner to gate |
| Diagnostic | Pool PF ~1.00 hid MR (COST-BOUND) vs trend (ANTI) |
| Limit-fill paper gate `eurusd_ny_mr_limit_fill_v1` | **FAIL → stop** |

### Paper-gate FAIL (last cost-side lever)

Source: `results/eurusd_ny_mr_limit_fill_paper_gate_v1.{json,md}`

| Comparison | Result |
|------------|--------|
| mean edge 11.50 vs mean RT 11.52 | **FAIL** (−0.01) |
| mean edge vs median RT | only mixed PASS (biased) |
| median edge 7.00 vs median RT 11.00 | **FAIL** (−4.00) binding |
| fill_rate 0.985 vs ≤0.70 validity | **FAIL** — not a limit model |

Honest prior confirmed: ~11.7 vs ~12 at zero slip — break-even at best, **not a business**.

---

## XAU closed screens / nulls (selected)

| Family / line | Disposition | Key numbers |
|---------------|-------------|-------------|
| `bb_rsi` | `KILL_BB_RSI_LINE` | max PF (n≥20) **2.242**; **p_max_pf=0.854**, p_n_passers=0.707 |
| Donchian / turtle | `KILL_DONCHIAN_LINE` | max PF **1.995**; **p_max_pf=0.195**, p_n_passers=0.293 |
| Walk-forward / holdout collapse | NO-GO | baseline train PF **1.837** → OOS PF **0.588** (n=7) |
| `asia_box_london_sweep_fade_flat` | SCREEN_FAIL | n=670, PF **0.553**, NP −8142, DD 82%; null skipped |
| `exog_london_fx_cosign_xau_follow_flat` | SCREEN_FAIL | pooled PF **0.903**, soft 0; best XAU pooled PF among recent family screens, still fail |
| `day_open_reclaim_flat`, `early_server_range_break_flat`, `server_hour_window_flat`, `tod_london_ny_flat`, `joint_london_open_cosign_fade_flat`, … | SCREEN_FAIL / invalid / superseded | see `results/xau_loop_status.md` + registry |

Null lesson: high in-sample max PF that fails max-stat is **search measuring itself**, not a market edge.

---

## Process wins (banked)

Any future **paper gate** must:

1. Require **mean-vs-mean and median-vs-median**, with **median binding**. Never mean-edge vs median-RT alone.
2. Treat **fill_rate ≳ 70%** as a **validity failure** for limit-fill studies — reject **before** reading edge.

Encoded in: `docs/research/EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md` (standing future rule) and `docs/research/XAU-FAMILY-PROTOCOL-V2.md` (pointer section).

**Simulator / diagnostic bias gates** (IDLE-compatible validation): `scripts/research_bias_gates.py` — `first_bar_exit_pct > 40%` and thin-n WR `>75%` with `n < 100`; plus thin-n positive edge labels (`CLEARS-FRICTION` / `COST-BOUND` with `n < 100`) auto-warned from `signal_edge_diagnostic` (would have flagged triage CLEARS at n=80/92 without a manual skeptic).

---

## Explicitly forbidden next moves

- Subset the 7,819 EURUSD MR signals  
- Invert any ANTI family  
- Retune / revive any closed `family_id` / `search_id`  
- Run a screen on a thesis that cannot clear friction **on paper** under a self-consistent gate  
- Relabel peeked windows as OOS  

---

## If research continues

Change **horizon / structure**, not the family class:

- Daily/weekly theses where ~22 pts is a small fraction of the move  
- Carry / rate differential, session–weekday seasonality at daily scale  
- Cross-instrument lead-lag at daily horizon  

Closest *structurally different* shape already in-repo: **exogenous predictor** (`exog_london_fx_cosign_*`) — not “indicator on own price.” It still SCREEN_FAIL’d (pooled PF 0.90); any sequel needs a **new** `family_id` and freeze-before-peek, not a retune.

Model-class map for that sequel (GARCH as sizing/stops, Kalman/rolling β as a **new** link family, then OU/coint spreads): [MATH-MODELS-ROADMAP.md](MATH-MODELS-ROADMAP.md). Design note only — not a screen authorization.

---

## Index of sources

| Topic | Path |
|-------|------|
| How to run each path | [HOWTO-BACKTEST-PATHS.md](HOWTO-BACKTEST-PATHS.md) |
| Math-model queue | [MATH-MODELS-ROADMAP.md](MATH-MODELS-ROADMAP.md) |
| Loop status | `results/xau_loop_status.md` |
| Triage | `docs/research/SIGNAL-EDGE-TRIAGE.md` |
| CLEARS skeptic | `docs/research/SIGNAL-EDGE-TRIAGE-SKEPTIC.md` |
| EURUSD screen | `results/eurusd_ny_scalp_autoresearch.md` |
| EURUSD diagnostic | `results/eurusd_ny_scalp_signal_diagnostic.md` |
| Limit paper gate | `results/eurusd_ny_mr_limit_fill_paper_gate_v1.md` |
| BB/RSI null | `results/xau_null_maxstat.md` |
| Donchian null | `results/xau_donchian_null_maxstat.md` |
| Walk-forward | `results/xau_retrain_walkforward_summary.md` |
| Asia-box screen | `results/xau_asia_box_london_sweep_fade_flat_null_maxstat.md` |
| Disposition registry | `results/xau_charter_disposition_registry.jsonl` |
