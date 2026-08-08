# XAU post-kill plan — costed re-eval of frozen lanes

**Date:** 2026-08-08  
**Context:** `KILL_BB_RSI_LINE` (p_max_pf=0.854, p_n_passers=0.707). Do not retune or promote bb_rsi.  
**Safety:** offline only · NEVER `--live` · holdout sealed for selection · frozen params only (no re-search).

---

## 1. Disposition snapshot

| Item | Value |
|------|--------|
| bb_rsi family | **KILL** — gates measured search, not market |
| Costs in CSV | measured spread (`spread` col); commission/slippage still 0 |
| `strategy_params.json` costs | `spread_col=spread`, `point_size=0.01`, `commission_per_lot=0`, `slippage_points=0` |
| `backtest.simulate()` | **charges** round-trip costs when configured |
| Lane deep-opt / multi-year | **frictionless** — see gap below |
| Standing loop status | RESEARCH_ONLY / promote=no / live_go=false |

---

## 2. Cost gap (confirmed)

### Grep: no cost wiring

| File | `spread` / `commission` / `trade_cost` / `slippage` |
|------|-----------------------------------------------------|
| `scripts/xau_lane_deep_opt.py` | **zero matches** |
| `scripts/xau_frozen_multi_year_eval.py` | **zero matches** |
| `scripts/xau_preregistered_holdout.py` | **zero matches** |

### Per-lane simulators (all in `xau_lane_deep_opt.py`)

| Function | Charges costs? | PnL form |
|----------|----------------|----------|
| `simulate_vol_gate` | **NO** | `(exit−entry)×CONTRACT×lots×pos` |
| `simulate_donchian` | **NO** | same (incl. partials) |
| `simulate_atr_trail` | **NO** | same |
| `simulate_htf_fib_enhanced` | **NO** | same |
| `simulate_htf_pullback` | **NO** | same |

`xau_frozen_multi_year_eval.py` imports those five sims and calls `sim(d, **params)` with catalog kwargs only — so the entire 8×9 multi-year matrix and deep-opt champions are **frictionless** and **unfalsifiable** under measured spread.

Contrast: `backtest.simulate` debits once per closed trade off the **entry bar**:

```text
trade_cost = (spread_pts[i] + 2*slippage_points) * point_size * CONTRACT_SIZE * lots
           + 2 * commission_per_lot * lots
pnl = (exit - entry) * CONTRACT_SIZE * lots * pos - trade_cost
```

That formula must be shared by every lane sim before any frozen re-eval is trusted.

---

## 3. Frozen catalog — costed re-eval list

Catalog: 8 entries. **None are bb_rsi** (kill already excludes that family). All remain eligible for **costed, no-retune** re-eval; priority follows multi-year skeptic signal.

| Priority | Catalog id | Lane | Why |
|:--------:|------------|------|-----|
| **P0** | `baseline_donchian_turtle` | donchian_turtle | Only multi-year +NP / PF>1 sign-stable (incl. 2023 pre-sample) |
| **P0** | `refined_donchian_exit_N8_gate_pass` | donchian_turtle | Same family; exit_N=8 refine — re-check under costs |
| **P1** | `baseline_atr_trail_breakout` | atr_trail_breakout | Strong IS; collapses 2023 — costs may kill remaining windows |
| **P1** | `refined_atr_pack_entry20_no_atr_floor` | atr_trail_breakout | Higher n; same fragility risk |
| **P2** | `baseline_htf_fib_xau` | htf_fib_xau | Thin n=17 baseline; cost bite per trade large |
| **P2** | `refined_htf_fib_best_gate_pass` | htf_fib_xau | Wider n; still uncosted |
| **P3** | `baseline_vol_gate_sparse` | vol_gate_sparse | PARK'd; costed develop replay only (no re-opt) |
| **P3** | `baseline_htf_pullback_new` | htf_pullback_new | PARK'd; high n → total spread drag may dominate |

**Exclude:** any bb_rsi / rsi_cross grid search, null max-stat re-run, further knob cuts on that line.

---

## 4. Implementation plan

### Files to edit

1. **`scripts/xau_lane_deep_opt.py`** (primary)
   - Add a shared helper (or inline params matching `backtest.simulate`):
     - `spread_col: str | None = None`
     - `point_size: float = 0.01`
     - `commission_per_lot: float = 0.0`
     - `slippage_points: float = 0.0`
   - Wire into **all five** sims: set `trade_cost` at entry; subtract on every close path (SL/TP/signal/partial/EOD).
   - Defaults remain frictionless so old call sites do not silently change until kwargs are passed.
   - Prefer one `_trade_cost(spread_pts, i, lots, ...)` helper so formula cannot drift from `backtest.py`.

2. **`scripts/xau_frozen_multi_year_eval.py`**
   - Load `costs` from `strategy_params.json` (same pattern as `xau_walkforward.py` / `xau_null_maxstat.py`).
   - Merge into `normalize_params` / `run_one` so every cell is costed.
   - Record `costs` block in output JSON meta.
   - Optionally write new artifacts (`*_costed.json` / `*_costed.md`) so frictionless history stays comparable — or overwrite with a clear `costs` field and timestamp.

3. **Do not edit for this fire**
   - `backtest.py` cost math (source of truth — leave unless sharing a tiny helper module).
   - bb_rsi / null max-stat scripts (closed).
   - Catalog params (frozen; no retune).
   - Holdout lock / virgin path.

### Optional (later, not blocking)

- Port the same kwargs into `scripts/xau_preregistered_holdout.py` lane sims if that path is reused.
- Commission sensitivity ($3–5/lot + 10–20 pt slip) once measured spread re-eval lands — same as bb_rsi sensitivity table.

### Re-eval command (after code change)

```bash
# offline, no retune, no --live
python3 scripts/xau_frozen_multi_year_eval.py
```

Expect outputs under `results/xau_frozen_multi_year_eval.json` (+ matrix CSV) with costed metrics. Re-read skeptic with **same windows / labels** (2024–25 IS; 2026_to_peek diagnostic only; 2023 best historical stress).

Smoke check that costs bite:

```bash
# Develop-only sanity: Donchian NP/PF must drop vs frictionless catalog develop_metrics
python3 -c "
import json, pandas as pd, sys
from pathlib import Path
sys.path[:0] = ['.', 'scripts']
from backtest import load_h1
from xau_lane_deep_opt import prepare_frame, simulate_donchian
from strategy_params import *  # if absent, load costs manually
costs = json.loads(Path('strategy_params.json').read_text())['costs']
d = prepare_frame(load_h1())
d = d[pd.to_datetime(d['time'], utc=True) < pd.Timestamp('2026-01-01', tz='UTC')]
cat = json.loads(Path('results/xau_frozen_champions_catalog.json').read_text())
p = {k:v for k,v in cat['entries'][1]['params'].items() if k != 'mode'}
m0 = simulate_donchian(d, **p)
m1 = simulate_donchian(d, **p, **costs)
print('frictionless', m0.net_profit, m0.profit_factor, m0.n_trades)
print('costed     ', m1.net_profit, m1.profit_factor, m1.n_trades)
assert m1.net_profit <= m0.net_profit + 1e-6
"
```

(Adjust import if `strategy_params` is JSON-only — load costs dict from file.)

---

## 5. Success criteria

| # | Criterion | Pass condition |
|---|-----------|----------------|
| 1 | Formula parity | Lane sims use the same round-trip debit as `backtest.simulate` |
| 2 | Costs applied | Re-eval meta records `spread_col=spread` (and commission/slip from params file) |
| 3 | No retune | Params only from `xau_frozen_champions_catalog.json` |
| 4 | Holdout sealed | No selection on `time >= 2026-01-01`; 2026_to_peek diagnostic only |
| 5 | Cost bite | At least P0 Donchian develop NP strictly lower than catalog frictionless figure |
| 6 | Decision | Per-lane: **keep research** if develop costed still clears soft gates **and** 2023 stress still +NP/PF>1; else **PARK/KILL lane** — never promote on IS alone |
| 7 | Promote path | Unchanged: virgin bars / sealed path only; **promote=no** unless future virgin hard_pass under **costed** sims |
| 8 | Safety | No `--live`, no orders |

### Expected outcomes (hypothesis, not gate)

- Donchian P0: most likely still +NP after ~$0.18 RT spread (high expectancy); may lose soft-pass cells at margins.
- atr_trail / fib / vol_gate / pullback: higher chance of PF flip or n-gated failure once friction is real — multi-year matrix already weak.

---

## 6. Out of scope this fire

- Re-running bb_rsi null / grid search  
- New lane design search  
- Live or paper GO  
- Commission measurement from executed deals (still broker contract; leave 0 + optional sensitivity)  
- Re-labeling IS years as OOS  

---

## 7. Next step after plan

1. Implement cost kwargs on the five lane sims.  
2. Re-run frozen multi-year eval costed.  
3. Hostile one-pager: which of the 8 survive measured spread; update `results/xau_loop_status.md`.  
4. Idle on virgin promote path until `n_virgin_bars` threshold — still costed when that day comes.
