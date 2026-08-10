# XAU post-kill executive summary

**Date:** 2026-08-08  
**Scope:** bb_rsi kill → costed re-eval of frozen multi-year lanes → disposition  
**Safety:** offline only · never `--live` · holdout sealed for selection · no retune

---

## 1. What was killed

| Item | Verdict |
|------|---------|
| **bb_rsi / vol-gate family** | **KILL_BB_RSI_LINE** — develop gate-passers were search artifacts, not market edge |
| Evidence | Null max-stat on ~1205 configs: real max PF 2.24 / 19 passers; null p50 max PF ≈3.0 / ≈22 passers; **p_max_pf=0.854**, **p_n_passers=0.707** |
| Walk-forward under costs | Already flipped negative (meanPF 1.32 → 0.79) before the null test sealed it |
| Action | Do **not** retune, cross-instrument, or promote this family |

Artifacts: `results/xau_null_maxstat.json`, `results/xau_null_maxstat.md`.

---

## 2. Costed re-eval (post-kill fire)

Prior multi-year matrix and lane deep-opt sims were **frictionless** (no spread debit). Plan
`results/xau_post_kill_plan.md` wired the five lane sims to the same round-trip formula as
`backtest.simulate`, then re-ran the frozen 8×9 matrix.

| Field | Value |
|-------|--------|
| **costs** | `spread_col=spread`, `point_size=0.01`, commission=0, slippage=0 |
| **cells** | 72 (8 catalog × 9 windows) |
| **hard_pass classic** | **2/72** (frictionless was **3/72**) |
| **soft_pass expectancy** | 13/72 |
| **promote** | **no** |
| **live_go** | **false** |

### Survivors vs deaths under measured spread

| Lane | Costed outcome |
|------|----------------|
| **donchian_turtle** (baseline + refined) | Only multi-year **sign-stable** 2023–2025 (+NP / PF>1) including pre-sample 2023; still + on peeked 2026; heavy DD remains |
| **htf_pullback** | **Dies** — 2023 sign flip under spread |
| **vol_gate sparse** | Calendar years still + but **develop_like dies**; lost 2023 hard_pass; family already null-killed — do not revive |
| **atr_trail** | Still collapses 2023 (regime-2025 story only) |
| **htf_fib** | Thin n or peek negative under costs — not multi-year robust |

Soft-pass count holding at 13 is not a rescue: almost all are Donchian on IS/peek windows.

Artifacts: `results/xau_frozen_multi_year_eval.json`, `results/xau_frozen_multi_year_matrix.csv`,
`results/xau_frozen_multi_year_costed_skeptic.md`.

---

## 3. Disposition

| Field | Value |
|-------|--------|
| **disposition** | **RESEARCH_ONLY** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **bb_rsi** | DEAD — closed |
| **remaining research candidate** | Donchian frozen only (necessary under spread, not sufficient for GO) |

---

## 4. What to do next

### Research (one decisive offline test)

**Donchian null / max-stat** — mirror `scripts/xau_null_maxstat.py` for the turtle lane only:

- develop only (`time < 2026-01-01`), holdout sealed  
- same measured-spread cost block  
- full Donchian grid, no early exit; return-shuffle nulls  
- kill if `p_max_pf` or `p_n_passers` > 0.05  

| Outcome | Action |
|---------|--------|
| Fail null | **KILL_DONCHIAN_LINE** → strategy-edge research idle; virgin WAIT_DATA for process only |
| Pass null | Keep frozen Donchian for **virgin-only** future eval — still **promote=no** until sealed virgin hard_pass under **costed** sims |

**Not next:** re-mining 2026_to_peek, re-labeling 2024–25 as OOS, reviving bb_rsi, ATR storytelling, another frictionless multi-year pass, paper/live GO.

### Housekeeping (non-research; does not advance promote)

| Item | Note |
|------|------|
| Charter / doctrine sync | Record KILL_BB_RSI_LINE, PARK pullback, costs defaults vs `xau_lane_opt_charter.json` |
| CSV / fit-window hygiene | Spread-bearing export; `slice_to_window` + sha256 on params |
| Multi-broker paths | Exness/install dirs, `MT5_BRIDGE_DIR` — platform ops |
| Lint | `uv run ruff check src tests` |

If the Donchian null is declined or already failed: **RESEARCH_IDLE** — only housekeeping + virgin data clock.

---

## 5. Safety

- No `--live`, no orders  
- No PAPER_GO / LIVE_GO from costed multi-year or bb_rsi null  
- Prefer virgin sealed hard_pass under costed sims ≫ any IS/peek narrative  

*One-liner: bb_rsi is dead; spread filters the rest down to Donchian as a null-test candidate — still research-only, still promote=no.*
