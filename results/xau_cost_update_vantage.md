# Vantage research costs update (XAU)

**Date:** 2026-08-08  
**Safety:** offline only — no re-search of bb_rsi / Donchian grids; no `--live`.

## Source of truth

| Artifact | Role |
|---|---|
| [`results/xau_research_costs.json`](xau_research_costs.json) | Research cost defaults (broker account-type commission + measured spread column) |
| [`scripts/xau_research_costs.py`](../scripts/xau_research_costs.py) | `load_research_costs()` → simulate kwargs; falls back to `strategy_params.json` costs |
| `strategy_params.json` → `costs` | Shipped baseline costs; `commission_per_lot` now **3.0** (RAW floor) |

## Owner-provided Vantage commission (account-type, not symbol-specific)

| Account type | Commission (per side per lot) | Research use |
|---|---|---|
| **RAW ECN** | **$3.00** | Default / conservative floor |
| **PRO ECN** | **$1.50** | Sensitivity only |

Slippage remains **0** until demo fills measure it.

## Round-trip formula

`backtest.simulate` (and the lane sims) charge once per closed trade:

```
trade_cost =
  (spread_pts + 2 * slippage_points) * point_size * CONTRACT_SIZE * lots
  + 2 * commission_per_lot * lots
```

Commission term only:

```
RT_commission_usd = 2 * commission_per_lot * lots
```

| Lots | RAW ECN RT | PRO ECN RT |
|---|---|---|
| 0.01 | **$0.06** | $0.03 |
| 1.00 | **$6.00** | $3.00 |

Spread is still charged from the per-bar `spread` column (`point_size=0.01`, XAU contract size 100).

## What changed

1. Wrote `results/xau_research_costs.json` (RAW default 3.0).
2. Set `strategy_params.json` `costs.commission_per_lot` → **3.0** (other cost fields unchanged).
3. Re-scored the **existing** bb_rsi params on their fit window under RAW commission and updated `metrics` so the reproduction tests stay consistent (no param re-search).
4. Documented 0 / PRO / RAW metrics in [`xau_cost_sensitivity_vantage.json`](xau_cost_sensitivity_vantage.json).
5. Pointed walk-forward / null-maxstat / Donchian-null / frozen multi-year / lane deep-opt at `load_research_costs()`.

## Dead baseline under RAW (documentation only)

bb_rsi is already null-killed (`KILL_BB_RSI_LINE`). Re-score on the recorded fit window:

| Commission | Net profit | PF | WR | DD% | n |
|---|---|---|---|---|---|
| 0 (spread only) | 1188.27 | 1.671 | 59.52 | 3.84 | 42 |
| 1.5 PRO | 1159.89 | 1.652 | 59.52 | 3.86 | 42 |
| **3.0 RAW** | **1138.56** | **1.637** | 59.52 | 3.88 | 42 |

Trade count is unchanged (costs do not alter entries). RAW costs ~$50 of the fit-window NP vs spread-only; classic gates still print green on this dead baseline — that is **not** a promote signal.

## Default reason

RAW ($3/side) is the **conservative research floor**. Use PRO ($1.5) only for explicit sensitivity comparisons, not as the default for new offline work.
