# Paper-gate declaration — EURUSD mean-reversion limit fill (v1)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Status** | **DECLARATION ONLY** — paper gate frozen; **no measurement yet**; no screen; no charter family freeze |
| **Proposed `search_id` / `family_id` (sketch)** | `eurusd_ny_mr_limit_fill_v1` |
| **Not a revival of** | `eurusd_ny_scalp_develop_v1` (closed SCREEN_FAIL) |
| **promote / live_go** | **false / false** |

## Honest prior (stated before any limit-fill number)

Market-next-open diagnostic on the **same** frozen `mean_reversion_signals` (develop `et_date < 2025-03-01`):

- Best horizon H50 mean edge ≈ **+11.7 pts**, t ≈ **+4.14**, positive in **4 of 5** develop years (medians as well as means).
- Round-trip friction under the closed lock: median spread ≈12 + 2×5 slip = **22 pts** → **COST-BOUND**.
- At **zero slippage**, paper RT ≈ **12 pts** vs ≈11.7 edge → **break-even at best**, not a business.
- This edge was measured **before** the 24-family triage sweep → does **not** carry that sweep's multiplicity debt.
- **Forbidden:** subsetting the 7,819 signals; inverting ANTI families; reopening the closed screen; holdout peek.

Any new family must earn its keep on the **cost / execution** side. If it cannot clear friction **on paper** before a screen is written, that is a cheaper SCREEN_FAIL than running one.

## Mechanism (imported — not reimplemented)

- Symbol / TF: EURUSD M5 (same data package as `results/eurusd_ny_scalp_lock.json`).
- Signal producer: `scripts/eurusd_ny_scalp_core.py::mean_reversion_signals` (BB pierce + RSI extremes). **Import only**; do not edit predicates for this paper gate.
- Session / one-per-day / clock: inherit the closed lock's session and clock contracts for the paper diagnostic unless a later full freeze amends them explicitly.

## Fill contract (frozen for the paper gate)

| Item | Rule |
|------|------|
| Limit price | **Signal bar close** (`close[i]`) |
| Long fill | Fill at `close[i]` iff `low[i+1] ≤ close[i]` (price trades through the limit on the next bar) |
| Short fill | Fill at `close[i]` iff `high[i+1] ≥ close[i]` |
| No-fill | **Skip** — not a trade; not replaced by market |
| No chase | Never fill at `open[i+1]` under this gate |
| Same ET day | `i+1` must be the same ET session-date as `i`; else skip |

## Cost book for the paper gate (frozen)

| Item | Rule |
|------|------|
| Slippage | **0** (limit; stated for paper gate — not a live claim) |
| Spread | Charge **1× spread_pts[i]** (entry bar) in points; no half-spread rebate unless later evidenced |
| Commission | 0 (Standard STP) |
| Paper RT (pts) | `spread_pts[i]` (per filled trade); report also the develop median of that RT |
| Forbidden | Assuming maker rebate / mid fill / always-filled |

## Edge measurement for the paper gate (frozen)

For each **filled** signal only:

```
r_h = (close[fill_index + h] - fill_price) * side / point
```

with `fill_index = i+1`, `fill_price = close[i]`, `point = 1e-5`.

Horizons: `{5,10,20,50,100}`. Develop mask only: `et_date < 2025-03-01`. Holdout **untouched**.

Report: n_signals, n_fills, fill_rate, mean/median/t per horizon, best/worst, median paper RT, verdict.

## Paper-gate pass rule

### As frozen for this run (v1 coded rule — flawed)

The first implementation compared **best-horizon mean edge ≥ median paper RT**, plus `n_fills ≥ 200`, `t ≥ 2`, not ANTI. That **mean-vs-median** pairing is structurally biased toward PASS when costs are right-skewed. It is retained here only as the historical coded rule for this artifact.

### Standing rule for any *future* paper gate (do not rewrite this run)

**PASS** only if all hold on develop:

1. `n_fills ≥ 200` (thin-fill fail-closed),
2. **fill_rate ≤ 0.70** (validity: above this, the study has not modelled a resting limit — reject **before** reading edge),
3. best-horizon **mean** edge **≥ mean** paper RT,
4. best-horizon **median** edge **≥ median** paper RT (**binding**),
5. that best-horizon **t ≥ 2.0** (with overlap caveat noted),
6. worst-horizon is **not** ANTI (`worst mean < 0` and `t ≤ −2`).

Never compare mean edge to median RT alone.

Otherwise **FAIL** → stop; do not write a screen; do not retune fill rules after seeing the number.

## Explicitly not authorized by this memo

- Full trading charter / exit grid / null / screen
- Editing `mean_reversion_signals`
- Holdout evaluation
- promote / live
- Revival of `eurusd_ny_scalp_develop_v1`

## Paper diagnostic result (2026-08-21) — **FAIL → stop**

**AUTHORIZED** and executed develop-only. Artifact: `results/eurusd_ny_mr_limit_fill_paper_gate_v1.{json,md}`.

| Field | Value |
|-------|--------|
| **pass_gate (coded mean vs median RT)** | labelled PASS (only mixed pairing) |
| **pass_gate (standing / adversarial)** | **FAIL** |
| n_signals / n_fills | 7819 / 7704 (fill_rate **0.985**) |
| mean / median paper RT | **11.52** / **11.00** pts |
| best H50 | mean **11.50** · median edge **7.00** · t **4.03** |
| mean edge vs mean RT | **FAIL** (−0.01) |
| median edge vs median RT | **FAIL** (−4.00) — binding |
| promote / live_go | false / false |

**Disposition:** FAIL → **stop**. No charter freeze, no screen. The cost-side lever was not actually tested (fill_rate 98.5% ≈ market fill with nicer price). Honest prior stands: ~11.7 vs ~12 at zero slip — break-even at best, not a business.

### Reusable lessons

1. Future paper gates: **mean-vs-mean and median-vs-median**, median binding.  
2. **Fill rate is a validity check**, not a vanity metric — ≳70% ⇒ reject before reading edge.
