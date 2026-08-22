# Paper-gate declaration — Daily FX cosign → next-day XAU follow (v1)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-22 |
| **Status** | **DECLARATION ONLY** — no measurement yet; no charter freeze; no screen |
| **Proposed `family_id` / `search_id` (sketch)** | `exog_fx_daily_cosign_xau_nextday_follow_flat` |
| **Not a revival of** | `exog_london_fx_cosign_xau_follow_flat` (H1 T*∈{7,8,9} follow, SCREEN_FAIL) |
| **promote / live_go** | **false / false** |

## Honest prior (from `BACKTEST-RECORD.md`)

- Intraday own-price families falsified under ~22 pt friction; MR edge saturates ~11.7 pts by H50.
- Closed H1 exogenous follow failed soft gates (pooled PF ~0.90).
- **Hypothesis for this gate:** moving the *same economic idea* (FX cosign → XAU follow) to **Daily** closes makes ~22 pts a small fraction of the day-range (~3% vs ~22% on M5/H1 holds) — a **horizon** change, not a retune of T* hours.
- Paper gate first (EURUSD MR lesson). FAIL → stop. No subsetting predictors post hoc.

## Why not a TF-retune of the closed family

| Closed H1 follow | This Daily proposal |
|------------------|---------------------|
| Signal at H1 T* ∈ {7,8,9} joint bar | Signal from **completed Daily** EUR+GBP close-open signs |
| XAU entry next H1 open, H=3 | XAU fill **D+1 Daily open**, exit **D+1 Daily close** |
| ATR SL/TP intraday | **No SL/TP** in the paper gate — signed open→close only |
| family_id `exog_london_fx_cosign_xau_follow_flat` | **New** `exog_fx_daily_cosign_xau_nextday_follow_flat` |

Hours are not the alpha here; **calendar-day closes** are.

## Data (frozen for the paper gate)

- Source: multi-instrument package `4f44b452081041f39fc24f03248b8ca8-ee2a993fb5b1befd` (XAUUSD/EURUSD/GBPUSD **H1**).
- **Daily bars:** derived per symbol per server calendar date:  
  `open = first H1 open`, `high = max H1 high`, `low = min H1 low`, `close = last H1 close`,  
  `spread_pts = last H1 spread` (conservative for RT; declare).
- Clock: `server_clock_as_stored` (same as package).
- Analysis calendar: **intersection** of the three Daily series on develop.
- Develop: `server_date < 2026-01-01` (package / XAU holdout lock). Holdout **untouched**.

## Signal / fill contract (frozen)

1. On day **D** (completed Daily bars for all three symbols):  
   `s_EUR = sign(close_EUR[D] - open_EUR[D])`, `s_GBP = sign(close_GBP[D] - open_GBP[D])`.  
   Require both **nonzero** and **equal** → cosign `s ∈ {+1,-1}`.
2. **No trade** if either FX is flat (0) or they disagree.
3. **Fill:** XAU at **open[D+1]** (next Daily open), side `s`.
4. **Exit:** XAU at **close[D+1]** (same session day). No SL/TP in the paper gate.
5. One signal per D; if D+1 missing on intersection → skip.
6. **Swap:** unmodeled (declare). Paper gate is open→close within D+1 only.

## Cost book for the paper gate (frozen)

| Item | Rule |
|------|------|
| Point | XAU `point_size = 0.01`, `contract_size = 100` (house) |
| Slippage | **Stated assumption** `slippage_points = 5` / side (same honesty as EURUSD lock — **not measured**) |
| Spread | `spread_pts` from XAU Daily bar (= last H1 spread that day) |
| RT (pts) | `spread_pts + 2 * slippage_points` |
| RT ($) | `RT_pts * 0.01 * 100 * lots` with **lots = 0.01** fixed for the paper gate (diagnostic scale) |
| Commission | 0 (Standard STP) |

**Caveat:** 10 pts of default RT are assumed slip. Report results at slip ∈ {0, 5, 10} as sensitivity; **binding gate uses slip=5**.

## Edge measurement (frozen)

For each filled event:

```
r_pts = (close_XAU[D+1] - open_XAU[D+1]) * s / point_size
```

Develop only. Report n_signals, mean/median/t of `r_pts`, mean/median RT_pts, and the four comparisons (mean/mean, mean/median, median/mean, median/median).

## Paper-gate pass rule (standing protocol)

**PASS** only if all hold on develop (slip=5 binding):

1. `n_fills ≥ 40` (Daily thin-n — fail-closed; not a waiver),
2. **mean** edge ≥ **mean** RT (pts),
3. **median** edge ≥ **median** RT (pts) — **binding**,
4. best (here only horizon = 1 day) **t ≥ 2.0**,
5. Not ANTI (mean < 0 and t ≤ −2).

Never mean-edge vs median-RT alone.  
(Fill-rate N/A — this is not a limit study.)

Otherwise **FAIL → stop**. Do not write a screen; do not retune symbols/sign/hold after seeing the number.

## Explicitly forbidden

- Peek holdout  
- Revive / rename closed H1 exog family  
- Subset days (DOW filters, volatility filters) after seeing edge  
- ATR/exit grid before paper PASS + separate full freeze  
- promote / live  

## Immediate next

1. Adversarial read of this declaration.  
2. On **`AUTHORIZE PAPER DIAGNOSTIC`**: one develop-only run; artifact under `results/`.  
3. FAIL → archive. PASS → only then full exogenous charter freeze (null method, H, costs) under a new authorization.

## Paper diagnostic result (2026-08-22) — **FAIL → stop**

**AUTHORIZED** and executed develop-only. Artifact: `results/exog_fx_daily_cosign_xau_nextday_paper_gate_v1.{json,md}`.

| Field | Value |
|-------|--------|
| **n_fills** | 842 |
| **edge mean / median (pts)** | 36.93 / 26.50 |
| **t** | **0.395** |
| **RT mean / median (slip=5)** | 25.94 / 28.00 |
| **median vs median** | **FAIL** (−1.50) binding |
| **mean vs mean** | PASS (+10.99) but t fails |
| **disposition** | **FAIL** |
| **promote / live_go** | false / false |

Even at **slip=0**, gate fails (t≪2). Typical trade after costs is negative at binding slip. **Stop** — no charter freeze, no screen, not a revival of H1 exog follow.
