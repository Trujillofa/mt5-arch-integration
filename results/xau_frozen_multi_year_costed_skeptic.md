# XAU Frozen Multi-Year Eval — Costed Hostile Skeptic

**Date:** 2026-08-08  
**Stance:** Fail closed. Prior frictionless multi-year autopsy (`xau_frozen_multi_year_skeptic.md`) is superseded for **edge magnitude** by this re-run; independence labels and promote doctrine are unchanged. Costs do not mint independence.

**Pipeline phase:** Offline re-score of the same 8 frozen catalog configs × 9 windows with measured spread charged (`spread_col=spread`, `point_size=0.01`). Commission and slippage still **0** (not obtainable from history). No retune. No `--live`.

**Artifacts reviewed:**

| Path | Role |
|------|------|
| `results/xau_frozen_multi_year_eval.json` | Costed cells + hard/soft gates (this re-run) |
| `results/xau_frozen_multi_year_matrix.csv` | Compact costed PF/WR/DD/n/NP matrix |
| `results/xau_frozen_multi_year_skeptic.md` | Prior **frictionless** multi-year skeptic |
| `results/xau_null_maxstat.md` | bb_rsi / vol-gate family **DEAD** (null max-stat) |
| `results/xau_loop_status.md` | Loop disposition; costs + KILL_BB_RSI_LINE |

**Costs meta (from eval):**

```json
{
  "spread_col": "spread",
  "point_size": 0.01,
  "commission_per_lot": 0.0,
  "slippage_points": 0.0
}
```

Median XAUUSD H1 spread ~18 pts (~$0.18 RT) per loop status. This skeptic is **spread-only** — further commission/slip would only erode more.

**bb_rsi line:** `KILL_BB_RSI_LINE` (`xau_null_maxstat.md`). Do **not** revive, retune, or cross-instrument that family. Vol-gate cells below are catalog diagnostics only.

---

## Executive summary

| Question | Verdict |
|----------|---------|
| What changed vs frictionless multi-year? | Edge **eroded everywhere**; hard_pass **3 → 2**; one pre-sample sign flip (pullback 2023) |
| Sign-stable after spread (2023–2025 PF>1 & NP>0)? | **Donchian only** (baseline + refined). Vol-gate year signs hold but **develop_like dies**. Fib thin-n + only. |
| Who dies under costs? | **htf_pullback** (2023 flip); **vol_gate develop aggregate**; ATR still collapsed 2023; refined fib still fails peeked 2026 |
| Unlocks PAPER_GO / LIVE_GO? | **NO** |
| **promote** | **no** |
| **live_go** | **false** |
| **next_step** | **Donchian null / max-stat** (one decisive offline test) — only remaining interesting lane |

**One-line:** After measured spread, only Donchian keeps multi-year +NP/PF>1 through pre-sample 2023; pullback and long-path vol-gate die; bb_rsi already null-killed — **promote=no / live_go=false**; next: Donchian null max-stat only.

---

## 1. Protocol (unchanged contamination map)

Same as frictionless skeptic §1:

| Window | Independence |
|--------|----------------|
| `year_2023` | Pre-sample stress on frozen params (best historical non-IS year) |
| `year_2024`, `year_2025`, halves | Largely **in-sample** for develop-selected champs |
| `year_2026_to_peek` | **Peeked** holdout-era — diagnostic only |
| `develop_like` / `full_available` | Ranking echo / narrative, not sealed OOS |

Selection still develop-only (`time < 2026-01-01`). Re-scoring with costs is **not** a new confirmatory experiment.

Aggregate (costed):

| Stat | Frictionless prior | Costed re-run |
|------|--------------------|---------------|
| Cells | 72 | 72 |
| `n_hard_pass_classic` | **3** | **2** |
| `n_soft_pass_expectancy` | 13 | **13** |

Hard-pass classic under costs (PF>1.5, WR>55, DD<10, n≥20):

| Config | Window | Note |
|--------|--------|------|
| `baseline_vol_gate_sparse` | `year_2026_to_peek` | Contaminated HO-era; n=20 knife-edge |
| `baseline_htf_pullback_new` | `h2_2025` | IS half-year only |

**Lost under costs:** `baseline_vol_gate_sparse` on `year_2023` (frictionless PF≈1.51 hard_pass → costed PF **1.384**, fails PF gate). Pre-sample classic hard_pass for vol-gate is **gone**.

---

## 2. Costed year matrix (PF / NP / n)

Source: `xau_frozen_multi_year_matrix.csv`. Sign-stable = PF>1 **and** NP>0 on every full year **2023–2025**.

| Config | 2023 | 2024 | 2025 | 2026_peek | Costed stability |
|--------|------|------|------|-----------|------------------|
| `baseline_vol_gate_sparse` | 1.38 / +402 / 37 | 1.34 / +285 / 26 | 1.19 / +167 / 34 | 2.07 / +398 / 20 | Year signs **hold** but **decay**; `develop_like` **PF 0.97 / −133** — long path dies |
| `baseline_donchian_turtle` | 1.36 / +2316 / 96 | 1.32 / +1888 / 107 | 2.12 / +8968 / 100 | 1.61 / +1498 / 48 | **Sign-stable** all years + peek; DD heavy (2023 21%, develop 30%) |
| `baseline_atr_trail_breakout` | **0.69 / −398 / 16** | **0.97 / −67 / 28** | 2.47 / +3607 / 29 | 5.10 / +570 / **4** | **Collapses 2023–24** (unchanged thesis) |
| `baseline_htf_fib_xau` | 1.38 / +387 / 16 | 1.05 / +48 / 13 | 5.61 / +1349 / 10 | 2.37 / +915 / 14 | Sign + but **n too small** every year |
| `baseline_htf_pullback_new` | **0.97 / −141 / 110** | 1.26 / +2128 / 158 | 1.30 / +2471 / 173 | **0.79 / −299 / 31** | **Dies under costs in 2023**; peek still dead |
| `refined_donchian_exit_N8…` | 1.34 / +2129 / 102 | 1.51 / +3037 / 108 | 2.17 / +9465 / 104 | 1.42 / +1022 / 53 | **Sign-stable** like baseline turtle |
| `refined_atr_pack_entry20…` | **0.88 / −481 / 45** | 1.40 / +2157 / 62 | 2.44 / +9816 / 67 | 1.21 / +344 / 17 | **Collapses 2023**; 2025-centric |
| `refined_htf_fib_best…` | 1.19 / +1113 / 87 | 1.12 / +733 / 88 | 1.41 / +1960 / 79 | **0.98 / −56 / 51** | Mild IS +; **peek negative** under costs |

Frictionless → costed deltas (illustrative, calendar years):

| Config / year | Frictionless (approx) | Costed | Δ |
|---------------|----------------------|--------|---|
| vol_gate 2023 | PF 1.51 / +518 | 1.38 / +402 | lost hard_pass |
| pullback 2023 | PF 1.01 / +43 | **0.97 / −141** | **sign flip** |
| donchian 2023 | PF 1.42 / +2630 | 1.36 / +2316 | eroded, still + |
| vol_gate develop_like | PF ≈1.03 | **0.97 / −133** | aggregate **dies** |

---

## 3. Which lanes remain sign-stable after spread

**Strict multi-year sign-stable (2023–2025, PF>1 and NP>0) under measured spread:**

1. **`donchian_turtle` baseline** — only clear multi-year profit-sign continuity after costs; still + on peeked 2026 (PF 1.61). Soft expectancy passes on 2025 / halves / peek (IS/peek cluster). Classic WR>55 gate remains mismatched for turtles. DD remains severe on long windows (develop ~30%).
2. **`refined_donchian_exit_N8_gate_pass`** — same family; soft-pass cluster on 2024–2025 (IS). Not more independent than baseline; slightly weaker 2023 PF than frictionless but still clearly +.

**Borderline / do not count as robust multi-year:**

| Config | Why not “stable survivor” |
|--------|---------------------------|
| `baseline_vol_gate_sparse` | Calendar years still +NP, but PF decays (1.38→1.34→1.19) and **`develop_like` is net-negative** under spread. Pre-sample hard_pass lost. Catalog is vol_gate / BB family — **bb_rsi line already null-killed**; do not revive or re-search this family. |
| `baseline_htf_fib_xau` | Sign + but n≈10–16/year — noise-adjacent; not a stability claim. |

---

## 4. Which lanes die under costs

| Config / lane | Death mode under spread | Read |
|---------------|-------------------------|------|
| **`baseline_htf_pullback_new`** | **2023 sign flip** (+43 → −141); peek still −299 | Pre-sample edge was friction illusion; stay PARK / dead for multi-year claim |
| **`baseline_vol_gate_sparse`** | `develop_like` **NP− / PF<1**; lost 2023 hard_pass | Not a long-path survivor; family already KILL via null max-stat on bb_rsi grid |
| **`baseline_atr_trail_breakout`** | Still **2023–24 collapse** (worse NP) | Regime-2025 story only; not multi-year |
| **`refined_atr_pack_entry20…`** | Still **2023 collapse** | Refine did not buy pre-sample robustness |
| **`refined_htf_fib_best…`** | Peek **negative** under costs (−56) | Mild IS only; not confirmatory |
| **bb_rsi / shipped baseline family** | Null max-stat: p_max_pf **0.854**, p_n_passers **0.707** | **DEAD** — do not revive (separate fire; binding) |

Soft-pass count staying at 13 is **not** a rescue: those cells are almost all donchian on IS halves / 2025 / peeked 2026 — same contamination as before, just thinner edge.

Commission/slip still at 0: any real RT account floor ($3–5/lot + slip) would further tax high-n turtle paths. Costed-positive Donchian is **necessary but not sufficient**.

---

## 5. Explicit promote ruling

### promote = **no** · live_go = **false** · PAPER_GO = **no**

This costed multi-year re-run does **not** unlock paper or live. Reasons (any one would suffice):

1. **2024–2025 remain non-independent** of develop selection.
2. **2026_to_peek remains contaminated** — one hard_pass there is worthless for promote.
3. **No sealed virgin** post-peek window with adequate bars.
4. Costs **reduced** gate hits and **killed** pullback pre-sample / vol-gate long path — they did not create new independence.
5. **bb_rsi line is null-dead**; do not launder promote through vol_gate catalog cells.
6. Donchian multi-year +NP under spread is a **research survivor flag**, not a sealed OOS proof (multiplicity, IS years, heavy DD, commission unmeasured).

| Gate | Status |
|------|--------|
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **LIVE_GO** | **false** |
| Disposition | **RESEARCH_ONLY** |

Safety: offline only; never `--live` without explicit skeptic LIVE_GO (there will not be one from this artifact).

---

## 6. next_step

**Only remaining interesting lane after spread:** Donchian (baseline and/or refined frozen). ATR / pullback / refined fib / vol-gate-as-family are not multi-year survivors under costs; bb_rsi is null-killed.

### ONE decisive offline test

**Donchian null / max-stat** (mirror of `scripts/xau_null_maxstat.py` protocol, turtle lane only):

- Window: develop only (`time < 2026-01-01`), holdout sealed  
- Costs: same measured spread block as this eval (commission/slippage 0 unless later measured)  
- Grid: full Donchian / turtle parameter grid used in deep-opt lineage (no early exit; fixed seed)  
- Null: return-shuffle trials; report `p_max_pf` and `p_n_passers` with n≥20 gate  
- Kill rule: fail if either p > 0.05 (same as bb_rsi null doc)  
- **No retune on holdout; no virgin mining; no `--live`**

| Outcome | Action |
|---------|--------|
| Fail null (p large) | **KILL_DONCHIAN_LINE** → research idle on strategy edge; virgin WAIT_DATA only for process completeness |
| Pass null (both p ≤ 0.05 and n_passers > null p90) | Permission to **keep** Donchian frozen for virgin-only future eval — still **promote=no** until sealed virgin hard_pass |

If that single test is already done and failed, or is declined: **RESEARCH_IDLE** (no further lane research; housekeeping only).

**Not next_step:** re-mining 2026_to_peek, re-labeling 2025 as OOS, reviving bb_rsi, ATR regime storytelling, or another frictionless multi-year pass.

---

## 7. Open housekeeping (non-research)

These do **not** advance edge claims or promote. Track separately from the research loop:

| Item | Note |
|------|------|
| **Charter PR / doctrine sync** | `xau_lane_opt_charter.json` vs actual discard policy (KILL_BB_RSI_LINE, PARK pullback, costs defaults); platform charter vs research layer boundaries |
| **CSV history hygiene** | Spread-bearing re-export already in play; fit-window / sha256 discipline on `strategy_params.json`; do not extend CSV under frozen metrics without `slice_to_window` |
| **Exness symbols / multi-broker paths** | Brand install dirs, `MT5_BRIDGE_DIR`, broker env scripts — ops/platform, not XAU edge |
| **Ruff / lint** | `uv run ruff check src tests` — code quality only |

---

## 8. Checklist vs assigned requirements

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Lanes sign-stable after spread | **§3** — Donchian baseline + refined only |
| 2 | Lanes that die under costs | **§4** — pullback 2023, vol_gate develop_like, ATR 2023, refined fib peek; bb_rsi null-dead |
| 3 | Explicit promote=no / live_go=false | **§5** |
| 4 | next_step one decisive offline test or RESEARCH_IDLE | **§6** — Donchian null max-stat |
| 5 | Open housekeeping non-research | **§7** — charter PR, CSV history, Exness symbols, ruff |

---

## 9. Disposition

| Field | Value |
|-------|--------|
| **ok (artifact written)** | true |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | no |
| **bb_rsi** | DEAD — do not revive |
| **summary / next_step** | Donchian null max-stat (spread-costed, develop-only); else RESEARCH_IDLE |

*Hostile one-liner: Spread turns multi-year “depth” into a filter — pullback and long-path vol-gate fail it; only Donchian still prints green through 2023, and that is a null-test candidate, not a live ticket.*
