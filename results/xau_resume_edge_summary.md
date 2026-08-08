# XAU resume-edge summary

**Date:** 2026-08-08  
**Workflow:** `.grok/workflows/xau-resume-edge.rhai`  
**Branch:** `research/algo-trading-btc-gold-forex`  
**Safety:** offline only · promote=no · live_go=false · no `--live`

## Outcome

| Field | Value |
|-------|--------|
| **commission default** | Vantage **RAW ECN $3.00 / side / lot** (`results/xau_research_costs.json`) |
| **family** | `prior_day_high_break` (charter-frozen, 3-config grid) |
| **null disposition** | **`KILL_PRIOR_DAY_HIGH_BREAK`** |
| **p_max_pf** | 0.463 |
| **p_n_passers** | 1.000 |
| **real max PF (n≥20)** | 1.077 · soft passers 0 |
| **next_step** | **`RESEARCH_IDLE_PENDING_NEW_THESIS`** |
| **promote / live_go / PAPER_GO** | no / false / no |

Null **KILL** → no costed walk-forward for this family. Do not retune, free knobs, or re-run frictionless. Next edge work needs a **new charter freeze** (new `family_id`). Dead lines: `bb_rsi`, Donchian/turtle, `prior_day_high_break`.

## What shipped (this fire)

1. **Costs** — RAW $3 research floor + PRO $1.5 sensitivity; helper `scripts/xau_research_costs.py`; walk-forward / null / multi-year / lane scripts load it; `strategy_params.json` commission_per_lot → 3.0 (metrics re-scored on fit window only).
2. **Charter** — `results/xau_next_design_charter.{md,json}` freezes `prior_day_high_break`.
3. **Scaffold** — `scripts/xau_null_core.py` + `scripts/xau_family_null_maxstat.py` (reusable family null max-stat); stub smoke artifacts under `results/xau_stub_null_maxstat.*`.
4. **First family** — `scripts/xau_family_prior_day_high_break.py` + develop grid + full null (40 trials) under RAW costs.
5. **Status** — `results/xau_loop_status.md` prepended with cost update, family, KILL, next_step.

## Artifacts

| Path | Role |
|------|------|
| `results/xau_research_costs.json` | Cost source of truth |
| `results/xau_cost_update_vantage.md` | RAW vs PRO + RT formula |
| `results/xau_cost_sensitivity_vantage.json` | Dead bb_rsi baseline under 0 / PRO / RAW |
| `results/xau_next_design_charter.{json,md}` | Frozen next-design program |
| `results/xau_prior_day_high_break_develop_grid.json` | Full 3-config develop score |
| `results/xau_prior_day_high_break_null_maxstat.{json,md}` | Null protocol + p-values |
| `results/xau_prior_day_high_break_null_skeptic.md` | Hostile skeptic (KILL) |
| `results/xau_loop_status.md` | Loop disposition |
| `.grok/workflows/xau-resume-edge.rhai` | Resume workflow |

## Tests

`uv run pytest tests/test_xau_pipeline.py tests/test_cli_unit.py -q` → **15 passed**.

## Git

See commit on this branch with message covering RAW $3 + `prior_day_high_break` + `KILL_PRIOR_DAY_HIGH_BREAK`. Ordinary push only (no force).
