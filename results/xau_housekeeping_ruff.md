# Ruff housekeeping (research layer)

Date: 2026-08-08  
Scope: `backtest.py`, `fetch_data.py`, `live_trader.py`, `scripts/`  
Mode: safe `ruff check --fix` only (no `--unsafe-fixes`, no logic rewrites)

## Summary

| Metric | Count |
|--------|------:|
| Baseline (research targets) | 101 |
| Auto-fixed (`--fix`) | 49 |
| Remaining (research targets) | **62** |
| Platform `src` + `tests` | clean (0) |
| Tests `test_xau_pipeline` + `test_cli_unit` | **15 passed** |

Net: **101 → 62** remaining on research layer (−39). Ruff reported 49 fixes applied; a few E402 import-order findings appeared after import auto-fixes (fixer reordering relative to non-import statements), so remaining is 62 rather than 101−49.

## What was auto-fixed (safe)

Typical `[*]` codes from baseline:

- F541 f-string-missing-placeholders
- I001 unsorted-imports
- UP017 datetime-timezone-utc
- F401 unused-import
- UP035 deprecated-import
- SIM114 if-with-same-arms

## Remaining by rule (need human judgment / unsafe)

```
11  C408   unnecessary-collection-call (dict() → literal; style only)
10  F841   unused-variable (may be intentional debug / future use)
 8  SIM102 collapsible-if (nested guards; readability tradeoff)
 6  E741   ambiguous-variable-name (`l` for low — common OHLCV idiom)
 6  N803   invalid-argument-name (API-ish params; renames need call-site care)
 5  B905   zip-without-explicit-strict (behavior: adding strict= may raise)
 4  E402   module-import-not-at-top-of-file (often intentional after path bootstrap)
 3  SIM103 needless-bool
 2  N806   non-lowercase-variable-in-function
 2  N813   camelcase-imported-as-lowercase (`MetaTrader5 as mt5` is convention)
 2  SIM113 enumerate-for-loop
 1  C401   unnecessary-generator-set
 1  SIM108 if-else-block-instead-of-if-exp
 1  SIM222 expr-or-true
---
62 total
```

36 of these have hidden unsafe autofixes (`--unsafe-fixes`); left untouched per safety brief.

## Remaining by file (approx)

| File | n |
|------|--:|
| scripts/xau_lane_deep_opt.py | 14 |
| backtest.py | 9 |
| scripts/xau_new_design_search.py | 7 |
| scripts/xau_preregistered_holdout.py | 5 |
| live_trader.py | 5 |
| scripts/xau_train_only_retrain.py | 4 |
| fetch_data.py | 3 |
| scripts/xau_null_maxstat.py | 3 |
| scripts/xau_htf_fib_widen_entries.py | 3 |
| scripts/xau_donchian_null_maxstat.py | 3 |
| scripts/xau_walkforward.py | 2 |
| scripts/xau_regime_analysis.py | 1 |
| scripts/xau_donchian_expectancy_ablate.py | 1 |
| scripts/xau_atr_trail_trade_count.py | 1 |
| scripts/htf_fib_core.py | 1 |

## Verification commands

```bash
uv run ruff check backtest.py fetch_data.py live_trader.py scripts --statistics
uv run ruff check src tests   # must stay clean
uv run pytest tests/test_xau_pipeline.py tests/test_cli_unit.py -q
```

## Disposition

- Platform layer: **clean**
- Research layer: **62 remaining**, all non-safe-auto; leave for deliberate cleanup (naming, OHLCV `l`, `zip(strict=)`, bootstrap E402, unused vars)
- Behavior: **no intentional logic changes** (safe autofixes only)
- `ok=true` for this pass (platform ruff clean + tests pass)
