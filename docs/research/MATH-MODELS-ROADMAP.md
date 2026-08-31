# Math models — what to implement next (design note)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-23 |
| **Status** | Design note only — **no implementation in this PR** |
| **Standing** | `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` · **promote=no** · **live_go=false** |
| **Authority** | [XAU-FAMILY-PROTOCOL-V2.md](XAU-FAMILY-PROTOCOL-V2.md) · [BACKTEST-RECORD.md](BACKTEST-RECORD.md) · `results/xau_loop_status.md` |

This maps **which model class to build next in this repo, and how**. It does not authorize a screen, a retune, a notebook live-go, or a change to `src/mt5_arch`.

---

## Current stack

| Lane | What exists | Disposition |
|------|-------------|-------------|
| **XAU family protocol v2.2** | Charters in `results/xau_charters/`, sealed cycle `scripts/xau_sealed_family_cycle.py`, costs `results/xau_research_costs.json` (Vantage Standard STP; slip=0 **unmeasured**), holdout `results/xau_holdout_lock.json` (`2026-01-01`, never for selection) | **IDLE** · closed books stay closed (`asia_box_london_sweep_fade_flat` PF 0.553; `bb_rsi` / Donchian null-killed; walk-forward 1.837 → 0.588) |
| **Exogenous London FX → XAU follow** | Protocol [MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md](MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md); family `exog_london_fx_cosign_xau_follow_flat` v4; runner `scripts/xau_exogenous_predictor_screen.py`; predictors EURUSD+GBPUSD, traded XAUUSD; fixed same-sign threshold at \(T^*\) hours {7,8,9} | **SCREEN_FAIL** (pooled PF 0.903) · do **not** retune this `family_id` |
| **Joint London cosign fade** | `joint_london_open_cosign_fade_flat` v4 | **SCREEN_FAIL** · closed |
| **US-index session scalp** | Overlay `UsIndexSessionScalp` v1.40 (observe only); Python screens v1–v8; core `scripts/us_index_session_core.py` | **All missed 1%/20%** (v8: 0/32). v4 already skipped HMM. **Dead screen — do not stack models on it** |
| **EURUSD NY scalp** | [EURUSD-NY-SCALP-DESIGN.md](EURUSD-NY-SCALP-DESIGN.md); lock `results/eurusd_ny_scalp_lock.json`; paper gate [EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md](EURUSD-MR-LIMIT-FILL-PAPER-GATE-v1.md) | Screen **0/192**; MR paper gate **FAIL** (median edge 7 vs median RT 11; fill_rate 0.985 invalid as a limit). Closed |
| **HTF Fib** | `ForexHtfPivotsFib` + `scripts/htf_fib_core.py` (pivot at confirmation bar); offline `scripts/htf_fib_offline_backtest.py` | Observe + frictionless lock `results/htf_fib_offline_lock.json`. Not a sealed money screen |
| **Multi-instrument data** | Phase 0 package XAUUSD+EURUSD+GBPUSD H1, `results/instrument_data_packages/`, holdout server `2026-01-01` | Pipeline only — no thesis freeze |
| **Observe overlays** | Fib, US-index, `BtcTrendPullback`, `ForexSignalLogger` (never `OrderSend`); Wave B [WAVE-B-OBSERVE.md](WAVE-B-OBSERVE.md) | Chart/logger only · **not** a promote path |

Intraday indicator-on-own-price is **falsified as a class** after costs ([BACKTEST-RECORD.md](BACKTEST-RECORD.md)). Next work changes **horizon / structure / risk module**, not a closed book.

---

## Principles

1. **No universal best model.** Match class to job: vol → GARCH; time-varying link → Kalman/rolling β; spreads → OU + cointegration; regime gate → HMM; meta-label → tree model. Do not drop LightGBM on a dead ORB screen.
2. **Classical first.** GARCH + (OU/cointegration **or** HMM) **before** LightGBM **before** RL.
3. **Plug-in, not a signal dump.** Models attach as **filters / sizing / stops / meta-labels** on a **chartered** host. Unchartered “fit GARCH, long when σ is low” is out of scope.
4. **Same quality bar as XAU protocol.** Develop-only selection; replay `results/xau_research_costs.json` (or the lane lock) through `simulate()` / `size_lots`; `slice_to_window()` for any `strategy_params.json` replay; holdout untouched; `python3` not `uv run`; **no** `--live`; **no** live-go from notebooks.
5. **One model family per implementation PR**, with a **beat-the-baseline-after-costs** test (constant lot / ATR lot / fixed-threshold link — declared in the lock). Frictionless “edge” is not a passer.
6. **New `family_id` or locked risk module.** Never a silent tweak to a sealed thesis (no hours/SL/TP/occupancy retune; no rename of `exog_london_fx_cosign_xau_follow_flat`).
7. **US-index v1–v8 stay dead.** No GARCH/HMM/LGBM/RL on `ny_cash_orb_*` or `us_index_session_autoresearch_vN.py`.

---

## Now (next two implementation PRs — one each)

### 1. GARCH or EGARCH — *risk filter*, not a direction

**Job:** forecast σ on **XAUUSD H1** (`xauusd_data.csv` / Phase 0 package) and/or **EURUSD H1** from the multi-instrument package. Use σ̂ to **scale lots** and/or **widen/narrow stops** on a **new or still-open host**. Do not emit +1/−1.

**Eligible hosts:** a **new** chartered family, or a *sizing-only* replay of the shipped `strategy_params.json` window via `slice_to_window()` (signal frozen). **Not eligible:** any SCREEN_FAIL `family_id`, EURUSD NY MR / trend / breakout, US-index v1–v8.

**Baseline to beat (after Standard STP costs):** constant lot and/or ATR lot (`size_lots` in `scripts/xau_exogenous_predictor_core.py`). Same trades, only the risk layer changes.

### 2. Kalman or rolling β — London FX *link*, new family

**Job:** test a **time-varying** EUR/GBP → XAU link vs the **failed fixed same-sign threshold** at London \(T^*\).

**Must be a new `family_id`** (e.g. `exog_london_fx_tvbeta_xau_follow_flat`). Reuse exogenous protocol v1 (predictors EUR+GBP, traded XAU, Phase 0 package, next-bar entry, fixed-H occupancy, charter costs = research book). **Do not** reopen v4 SHA `3dec09ef…` or report pooled-only.

**Baseline to beat:** the same new charter’s **frozen control arm** (fixed cosign threshold), develop-only — not a re-score of the closed family artifact.

---

## Next thesis family

**OU + Johansen and/or Engle–Granger** on **EURUSD–GBPUSD–XAUUSD** spreads (pairs / stat-arb), **H1 or daily** (where ~22 pt FX RT is noise — see BACKTEST-RECORD). Size with **GARCH vol targeting** from the risk module above.

New `family_id` + thesis memo + charter **before** any develop PF. Use the Phase 0 intersection calendar. Do not reshape EUR/GBP into a derived XAU indicator (exogenous protocol forbids that). Do not fade/follow the closed London-open event set.

---

## Later (charter first)

| Model | Allowed use |
|-------|-------------|
| **2–3 state HMM** | Gate **trade vs flat** on a **new** family (or an explicitly open host). Not a retrofit on US-index v4’s ATR-regime stand-in. |
| **LightGBM meta-label** | On **HTF Fib** (`htf_fib_core` features only — do not re-derive pivots) and/or a **new** ORB family, **only after** a charter authorizes the label and the cost book. The frictionless Fib lock is **not** that book. |

---

## Skip for now

PPO / other RL, Transformers, rough Heston, jump-diffusion as **primary** research. They do not match the idle bar (closed families, cost locks, no live-go) and skip the classical queue.

---

## Implementation shape (when a later PR builds one)

| Piece | Where |
|-------|--------|
| Risk / filter module | `scripts/xau_garch_risk_filter.py` (GARCH) or `scripts/xau_family_<new_id>.py` (Kalman/OU family) |
| Thesis memo | `docs/research/` — `XAU-RISK-GARCH-FILTER.md` or `MULTI-INSTRUMENT-THESIS-<new_id>_v1.md` |
| Freeze | `results/xau_charters/YYYY-MM-DD_<id>_v1.json` **or** a lane lock `results/<module>_lock.json` (`promote=false`, `live_go=false`) |
| Artifacts | slim `results/*.json` + short `*.md`; no `*_full.json` trade dumps |
| Tests | `tests/test_<module>.py` — synthetic / causality / cost-lock / **beat-baseline-after-costs** |

**Hooks (do not invent a second protocol):**

- `python3` + host numpy/pandas; `src/mt5_arch` **must not** import this.
- Costs: `scripts/xau_research_costs.py` (`load_research_costs`, `refuse_mutated_research_costs`); charter `costs` **equal** `results/xau_research_costs.json`. EURUSD money scores use that book or a **new** lane lock — not the frictionless Fib lock, not a cut of `eurusd_ny_scalp_lock.json` to manufacture a passer.
- Window: `results/xau_holdout_lock.json` / Phase 0 `holdout_start_server`; `backtest.slice_to_window()` for baseline replay.
- Family path: freeze-before-peek → `--strict-charter --screen-only` → null only if primary passers ≥ 1 (`within_day_ohlc_increment_rotate_v1` or exogenous `conditional_fixed_signal_events_fixed_trades_v1`).
- Bias gates: `scripts/research_bias_gates.py`. Paper gates: mean-vs-mean **and** median-vs-median (median binding); limit `fill_rate ≳ 0.70` is invalid.
- Status: read `results/xau_loop_status.md`; this note does **not** flip `next_step` / `promote` / `live_go`.

**Beat-the-baseline test (required in the implementation PR):** same host trades, frozen costs, develop-only; model layer vs the lock’s control (constant/ATR lot, or fixed-threshold link). Fail → stop. No holdout search.

---

## Non-goals

- No strategy code, retunes, or live-go **in this docs PR** (or from any notebook).
- No `OrderSend`, no `--live`, no `src/mt5_arch` imports, no platform-layer risk engine.
- No revival of closed `family_id`s; no ANTI inversion; no US-index v1–v8 stacking.
- No unchartered signal dump; no frictionless passer; no holdout selection; no widening `n_trades_min` / cutting costs to dodge a fail.
- No Wave C / live EA; observe overlays stay read-only.
