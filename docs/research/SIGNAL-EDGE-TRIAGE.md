# Signal-edge triage (develop windows only)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Tool** | `scripts/signal_edge_diagnostic.py` (read-only measurement; writes nothing, ranks nothing, selects nothing) |
| **Command** | `python3 scripts/signal_edge_diagnostic.py --lane all --by-year` |
| **Scope** | Importable ±1 families only; develop masks per lane lock; **holdout never touched** |
| **Status** | Phase report. `promote=false`, `live_go=false`. No screen/grid/null re-run. No lock/charter edits. |

Reproduce:

```bash
python3 scripts/signal_edge_diagnostic.py --lane all --by-year
# EURUSD regression check (friction=22, develop < 2025-03-01):
python3 scripts/signal_edge_diagnostic.py --lane eurusd --by-year
```

---

## Method (unchanged)

Signed forward return from the fill bar (open of `i+1`), in points:

```
r_h = (close[i + 1 + h] - open[i + 1]) * side / point
```

Horizons `{5,10,20,50,100}`. Verdicts vs lock friction:

| Verdict | Rule |
|---------|------|
| **CLEARS-FRICTION** | `best mean ≥ friction` and `t ≥ 2.0` |
| **COST-BOUND** | best mean > 0 and < friction (and not ANTI) |
| **ANTI** | worst-horizon mean < 0 and `t ≤ −2.0` (tested before positive cases) |
| **DEAD** | otherwise (noise / undersampled / no usable edge) |
| **EMPTY** | zero develop signals |

---

## Family table (one row per measurable family)

Best horizon = argmax of mean edge across horizons (tool field). Edge/t are that horizon's mean and t-stat. Friction is the lane lock cost book.

| Lane | Family | n | Best H | Edge (pts) | t | Friction | Verdict |
|------|--------|--:|-------:|-----------:|--:|---------:|---------|
| eurusd | `trend_continuation` | 5379 | 5 | +0.06 | +0.03 | 22 | **ANTI** |
| eurusd | `mean_reversion` | 7819 | 50 | +11.75 | +4.14 | 22 | **COST-BOUND** |
| eurusd | `breakout` | 764 | 10 | +7.76 | +1.12 | 22 | **DEAD** |
| xau | `exog_london_fx_cosign_xau_follow_flat` | 885 | 20 | +70.19 | +0.83 | 18 | **DEAD** |
| us_index | `ny_cash_orb_vwap_ema_flat` | 149 | 10 | −695.10 | −0.85 | 80 | **DEAD** |
| us_index | `us_index_session_develop_v1` | 125 | 10 | −190.73 | −0.21 | 80 | **DEAD** |
| us_index | `ny_cash_vwap_bounce_rsi` | 65 | 100 | +1443.35 | +0.49 | 80 | **DEAD** |
| us_index | `ny_cash_ema_macd` | 55 | 50 | +3281.29 | +1.26 | 80 | **DEAD** |
| us_index | `ny_cash_liquidity_sweep` | 80 | 50 | +3883.44 | +2.44 | 80 | **CLEARS-FRICTION** |
| us_index | `ny_cash_fvg_mitigation` | 127 | 5 | −603.74 | −0.94 | 80 | **ANTI** |
| us_index | `us100_us30_divergence` | 150 | 100 | +2622.00 | +1.43 | 80 | **DEAD** |
| us_index | `exog_us30_ny_cash_cosign_us100_follow` | 176 | 100 | +2165.43 | +1.11 | 80 | **DEAD** |
| us_index | `vol_regime_orb` | 164 | 100 | −1835.78 | −0.89 | 80 | **DEAD** |
| us_index | `tick_proxy_cvd` | 144 | 10 | +836.13 | +0.92 | 80 | **DEAD** |
| us_index | `prior_poc_reversion` | 131 | 50 | +833.48 | +0.55 | 80 | **DEAD** |
| us_index | `ny_cash_gap_fade_adr` | 56 | 5 | −315.21 | −0.24 | 80 | **DEAD** |
| us_index | `htf_lock_orb` | 86 | 100 | −614.73 | −0.23 | 80 | **DEAD** |
| us_index | `daily_regime_switch:mom_or` | 19 | 100 | −9167.37 | −1.04 | 80 | **ANTI** |
| us_index | `daily_regime_switch:mr_gap` | 0 | — | — | — | 80 | **EMPTY** |
| us_index | `london_xau_fx_risk_gate` | 72 | 20 | −86.51 | −0.07 | 80 | **DEAD** |
| us_index | `ib_false_breakout_fade` | 140 | 20 | +2036.84 | +1.61 | 80 | **DEAD** |
| us_index | `m5_zscore_tick_vol_exhaustion` | 92 | 20 | +3856.11 | +2.24 | 80 | **CLEARS-FRICTION** |
| us_index | `h1_volatility_squeeze_breakout` | 14 | 5 | −568.21 | −0.13 | 80 | **DEAD** |
| us_index | `h4_impulse_fib_pullback` | 23 | 100 | +938.35 | +0.06 | 80 | **DEAD** |

**Counts:** 24 families measured — 17 DEAD, 1 COST-BOUND, 3 ANTI, 2 CLEARS-FRICTION, 1 EMPTY. By-year slices reported at H50 by the tool.

---

## Per-lane summary

### EURUSD (`friction=22`, develop `et_date < 2025-03-01`)

- **Regression OK** — see dedicated section below.
- `mean_reversion`: real positive edge (~half friction) → **COST-BOUND**. Does **not** reopen the closed screen; does **not** authorize revival of this family_id.
- `trend_continuation`: reliably wrong (worst H50 −11.85, t −3.13) → **ANTI**. Do **not** invert.
- `breakout`: undersampled / insignificant → **DEAD**.

### XAU (`friction=18`, develop `server_time < 2026-01-01`)

- Sole runnable producer `exog_london_fx_cosign_xau_follow_flat`: best H20 +70.19 pts, t +0.83 → **DEAD** (does not clear friction with usable t).
- Closed / embedded XAU families without exportable ±1 `signal_fn` are listed under Unmeasurable (finding, not omission).

### US index (`friction=80`, develop masks per family lock; V1 holdout 2026-06-01 / V4 2026-07-01)

- **CLEARS-FRICTION (2):**
  - `ny_cash_liquidity_sweep` — H50 +3883 pts, t +2.44, n=80
  - `m5_zscore_tick_vol_exhaustion` — H20 +3856 pts, t +2.24, n=92
  - Measurement only. Does **not** promote, does **not** authorize a new exit grid or live. Evidence for a possible future **NEW** `family_id` / search freeze if pursued separately — not revival of a closed screen.
- **ANTI (2):** `ny_cash_fvg_mitigation`, `daily_regime_switch:mom_or`. Do **not** invert.
- **EMPTY (1):** `daily_regime_switch:mr_gap` (n=0 develop signals).
- **DEAD (15):** remaining US families — no friction-clearing significant edge on develop.

---

## COST-BOUND does not authorize revival; ANTI must not be inverted

### COST-BOUND ≠ revive

A COST-BOUND verdict means the signed forward return is positive on develop but **strictly below** round-trip friction. That is evidence about information content vs the cost book — **not** a license to:

- reopen a closed screen / lock / search_id,
- retune exits, size, or halts on the same family_id,
- subset-slice the signal set post hoc,
- set `promote=true` or `live_go=true`.

If a cheaper execution model or different timeframe is hypothesized later, that is a **new** `family_id` / search freeze with variables named *before* looking. COST-BOUND on a closed family is archived measurement for that future thesis only.

### ANTI must not be inverted

ANTI means the worst horizon is significantly negative — the rule is reliably wrong on develop, not merely noisy. Post-hoc sign flip of a losing rule is textbook overfitting. Inversion is **forbidden** on this diagnostic. A reverse hypothesis, if ever interesting, must be a new pre-registered `search_id` with its own freeze — never an inverted alias of the ANTI family_id.

Standing: **`promote=false`, `live_go=false`.**

---

## Unmeasurable families (finding, not omission)

These were intentionally skipped: no exportable ±1 `signal_fn` the diagnostic can import, or never implemented / not a new family. Absence from the table above is a documented finding.

| Family | Reason |
|--------|--------|
| `bb_rsi` | `KILL_BB_RSI_LINE`; entry embedded in `backtest.simulate(mode='bb_rsi')`; no exportable ±1 `signal_fn` |
| `donchian_turtle` | `KILL_DONCHIAN_LINE`; logic in `simulate_donchian()`; no exportable ±1 `signal_fn` |
| `prior_day_high_break` | `KILL_PRIOR_DAY_HIGH_BREAK`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `tod_london_ny_flat` | `PROTOCOL_NULL_INVALID` / `SCREEN_FAIL`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `server_hour_window_flat` | `SCREEN_FAIL ZERO_PRIMARY_PASSERS`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `early_server_range_break_flat` | `SCREEN_FAIL`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `day_open_reclaim_flat` | `SCREEN_FAIL`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `joint_london_open_cosign_fade_flat` | `SCREEN_FAIL`; cosign fade inside `simulate_joint()`; no exportable ±1 `signal_fn` |
| `asia_box_london_sweep_fade_flat` | `SCREEN_FAIL`; entry embedded in `simulate()`; no exportable ±1 `signal_fn` |
| `macro_news_event_api` | skipped in lock (no usable news CSV / DISCARD surprise-drift); never implemented |
| `us_index_session_v4_cost_size_once` | diagnostic_replay of already-closed winners; not a new signal family |

Hard rule honored: **do not re-implement** closed-family signal logic inside the diagnostic. Import existing modules only; else `runnable=false` / skip with reason.

---

## EURUSD regression confirmation

`eurusd_regression_ok: true`

Develop `< 2025-03-01`, friction `22` pts — reproduced prior write-up
(`results/eurusd_ny_scalp_signal_diagnostic.md`):

| Family | Role checked | Horizon | Mean (pts) | t | Verdict |
|--------|--------------|---------|----------:|--:|---------|
| `trend_continuation` | ANTI worst | H50 | **−11.85** | **−3.13** | ANTI |
| `mean_reversion` | COST-BOUND best | H50 | **+11.75** | **+4.14** | COST-BOUND |
| `breakout` | DEAD worst | H50 | **−19.18** | **−1.68** | DEAD |

Full `--lane all` inventory: 24 families (17 DEAD, 1 COST-BOUND, 3 ANTI, 2 CLEARS-FRICTION, 1 EMPTY). XAU `exog_london_fx_cosign_xau_follow_flat` DEAD. US CLEARS-FRICTION: `ny_cash_liquidity_sweep`, `m5_zscore_tick_vol_exhaustion`. US ANTI: `ny_cash_fvg_mitigation`, `daily_regime_switch:mom_or`.

---

## What this does not authorize

- No promote, no `--live`, no order EA.
- No reopen of closed screens / locks; no charter or `xau_loop_status` edits.
- No screen / grid / null re-runs from this report.
- COST-BOUND does not revive a family_id.
- ANTI families must not be inverted.
- CLEARS-FRICTION is measurement evidence only — not a live gate and not a silent reopen of a prior US search.
