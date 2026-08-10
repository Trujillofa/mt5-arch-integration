# XAU Frozen Multi-Year Summary

**Date:** 2026-08-06  
**Pipeline:** offline multi-year matrix of 8 frozen catalog configs (no retune)  
**Disposition:** **RESEARCH_ONLY — promote=no**  
**live_go / paper_go:** **no** (never recommend `--live` from this pass)

| Phase | Ran | Result |
|-------|:---:|--------|
| DATA | true | H1 bars/year: **2023:5894 · 2024:5935 · 2025:5911 · 2026:3525** (`has_2023=true`) |
| EVAL | true | years: 2023, 2024, 2025, 2026_to_peek (+ develop_like, full, h2_2024, h1_2025, h2_2025); **hard_pass cells: 3/72** |
| SKEPTIC | true | Donchian sign-stable (+NP/PF>1) across years incl. pre-sample 2023; atr_trail collapses 2023; 2024–25 IS + 2026 peeked — **promote=no** |

---

## Headline

| Field | Value |
|-------|--------|
| Coverage | Full calendar **2023–2025** + partial **2026** (to peek end); 8 configs × 9 windows = **72** cells; no empty windows |
| Stability | **Donchian** (baseline + refined) only clear multi-year **sign-stable** (+NP and PF>1 on 2023–2025, still + on peek). **ATR trail** collapses in **2023**. Vol-gate signs hold but edge decays on full develop. |
| Promote | **no** — multi-year re-score is diagnostics / autopsy, not sealed OOS proof |

**One-liner:** 2023 is present and useful as pre-sample stress; Donchian keeps profit-sign across years; ATR dies in 2023; 2024–25 are largely in-sample and 2026 is peeked — **no PAPER_GO / LIVE_GO**.

---

## Plain language: what each window is

These labels matter more than the PF numbers.

| Window | What it is | Can it “prove” the strategy? |
|--------|------------|------------------------------|
| **year_2023** | **Pre-sample** — frozen params were **not** selected on full 2023 (deep export came after champ freeze; original develop path started ~2024-08). Honest historical stress. | Stronger **stress test**, still not a sealed forward promote alone |
| **year_2024** | **Mostly in-sample / contaminated as independent** — H2 and post-2024-08 overlap the develop selection path | **No** independent proof |
| **year_2025** | **In-sample (IS)** — fully inside `develop = time < 2026-01-01` selection era | **No** — re-running frozen params here is not multi-year confirmation |
| **h2_2024, h1_2025, h2_2025** | Half-year slices of the same develop era | Diagnostics only |
| **develop_like** | All bars with `time < 2026-01-01` | Ranking echo, not OOS |
| **year_2026_to_peek** | **Peeked holdout era** — already seen in shortlist OOS / preregistered HO / deep-opt peeks through ~2026-08-06 18:00 | **Diagnostic only** — never promote on this alone |
| **full_available** | Pre-sample + IS + peeked mixed | Narrative only |

**IS vs peeked (short):**

- **In-sample (IS):** years/halves that overlap the data used (or available) when champions were chosen on develop. Good numbers here often mean “we already optimized near this path,” not “the future works.”
- **Peeked:** 2026-01+ already inspected in earlier offline fires. Scoring it again does **not** create a virgin out-of-sample result.
- **Pre-sample 2023:** best historical stress we have without refit — still not a substitute for a **sealed virgin** window after last peek.

---

## Data coverage

Source: `results/xau_history_coverage.json` · eval windows from `xau_frozen_multi_year_eval.json`

| Field | Value |
|-------|--------|
| Symbol / TF | XAUUSD H1 |
| Span | 2021-09-01 → 2026-08-06 |
| `n_h1` | 29151 |
| Source | Wine Vantage export `InpMonths=60` (no invented bars) |
| `has_2023` | **true** |

| Year | H1 bars |
|------|--------:|
| 2023 | 5894 |
| 2024 | 5935 |
| 2025 | 5911 |
| 2026 (partial in coverage) | 3525 |
| `year_2026_to_peek` window bars | 3523 (through last peek ~2026-08-06 18:00) |

`windows_skipped_empty`: **[]**. Multi-year depth is available; depth ≠ independence (see window table above).

---

## Catalog (frozen — no retune)

Source: `results/xau_frozen_champions_catalog.json` · 8 entries

| id | lane | role |
|----|------|------|
| `baseline_vol_gate_sparse` | vol_gate_sparse | baseline_champion |
| `baseline_donchian_turtle` | donchian_turtle | baseline_champion |
| `baseline_atr_trail_breakout` | atr_trail_breakout | baseline_champion |
| `baseline_htf_fib_xau` | htf_fib_xau | baseline_champion |
| `baseline_htf_pullback_new` | htf_pullback_new | baseline_champion |
| `refined_donchian_exit_N8_gate_pass` | donchian_turtle | refined_develop |
| `refined_atr_pack_entry20_no_atr_floor` | atr_trail_breakout | refined_develop |
| `refined_htf_fib_best_gate_pass` | htf_fib_xau | refined_develop |

Safety line (eval): `offline only; NEVER retune; NEVER --live; params only from frozen catalog`.

---

## Aggregate gates

Classic hard_pass: **PF>1.5, WR>55, DD<10, n≥20**  
Soft_pass expectancy (turtle/atr-like): **PF≥1.5, n≥40, DD≤12, exp≥20**

| Stat | Value |
|------|------:|
| Cells | 72 (8 × 9) |
| Classic hard_pass | **3** |
| Soft_pass expectancy | **13** |

### Hard-pass cells (3)

| Config | Window | Independence | PF | WR | DD% | n | NP |
|--------|--------|--------------|-----|-----|-----|---|-----|
| `baseline_vol_gate_sparse` | year_2023 | Pre-sample | 1.51 | 70.3 | 2.02 | 37 | +518 |
| `baseline_vol_gate_sparse` | year_2026_to_peek | **Peeked** | 2.12 | 80.0 | 1.43 | 20 | +414 |
| `baseline_htf_pullback_new` | h2_2025 | **IS half** | 1.59 | 55.4 | 3.63 | 74 | +1761 |

None of these unlock promote: one is research-stress (2023), one is peeked 2026, one is IS H2-2025.

---

## Per lane × year metrics

Metrics: **PF / WR% / DD% / n / NP**. Source: `results/xau_frozen_multi_year_matrix.csv`.

### Calendar years (primary multi-year view)

| Config | 2023 | 2024 | 2025 | 2026_to_peek (peeked) | Stability |
|--------|------|------|------|----------------------|-----------|
| **baseline_vol_gate_sparse** | 1.51 / 70.3 / 2.02 / 37 / **+518** | 1.40 / 65.4 / 4.17 / 26 / **+332** | 1.26 / 70.6 / 5.34 / 34 / **+234** | 2.12 / 80.0 / 1.43 / 20 / **+414** | Sign-stable 2023–25 (PF>1, +NP); PF **decays** into IS; develop_like PF≈1.03 |
| **baseline_donchian_turtle** | 1.42 / 30.2 / 19.8 / 96 / **+2630** | 1.38 / 35.5 / 12.0 / 107 / **+2221** | 2.16 / 41.0 / 8.97 / 100 / **+9213** | 1.64 / 39.6 / 8.15 / 48 / **+1576** | **Most stable** +NP/PF>1 all years; heavy DD in 2023 |
| **baseline_atr_trail_breakout** | **0.71 / 43.8 / 8.38 / 16 / −361** | **0.99 / 35.7 / 10.3 / 28 / −19** | 2.46 / 51.7 / 9.43 / 29 / **+3605** | 5.13 / 75.0 / 2.78 / **4** / +572 | **Collapses 2023–24**; 2025 hero; peek n underpowered |
| **baseline_htf_fib_xau** | 1.45 / 37.5 / 2.94 / 16 / +445 | 1.09 / 30.8 / 5.17 / 13 / +74 | 5.70 / 70.0 / 3.62 / 10 / +1360 | 2.41 / 50.0 / 2.20 / 14 / +928 | Sign +NP but **n too small** yearly |
| **baseline_htf_pullback_new** | 1.01 / 45.5 / 9.04 / 110 / +43 | 1.29 / 51.3 / 7.77 / 158 / +2401 | 1.33 / 51.4 / 8.11 / 173 / +2735 | **0.80 / 38.7 / 7.60 / 31 / −288** | Mild + on develop years; **collapses peeked 2026** |
| **refined_donchian_exit_N8…** | 1.42 / 31.4 / 21.1 / 102 / **+2602** | 1.56 / 38.0 / 11.4 / 108 / **+3308** | 2.20 / 40.4 / 7.58 / 104 / **+9610** | 1.44 / 37.7 / 8.07 / 53 / **+1055** | **Sign-stable** like baseline turtle; soft-pass cluster on IS |
| **refined_atr_pack_entry20…** | **0.90 / 37.8 / 23.7 / 45 / −365** | 1.42 / 41.9 / 18.0 / 62 / +2242 | 2.45 / 50.7 / 10.1 / 67 / **+9897** | 1.21 / 41.2 / 14.2 / 17 / +354 | **Collapses 2023**; 2025-centric; peek weak |
| **refined_htf_fib_best…** | 1.26 / 37.9 / 10.9 / 87 / +1454 | 1.16 / 36.4 / 8.23 / 88 / +961 | 1.45 / 40.5 / 8.40 / 79 / +2096 | **1.00 / 33.3 / 13.2 / 51 / −9** | Mild + IS; **flat/collapse on peeked 2026** |

### Half-year & aggregate windows (diagnostics)

| Config | h2_2024 | h1_2025 | h2_2025 | develop_like | full_available |
|--------|---------|---------|---------|--------------|----------------|
| baseline_vol_gate_sparse | 1.70 / 72.7 / 1.96 / 11 / +203 | 0.78 / 63.2 / 5.34 / 19 / **−139** | 2.41 / 80.0 / 1.42 / 15 / +374 | 1.03 / 62.9 / 11.1 / 132 / +130 | 1.13 / 65.4 / 11.1 / 156 / +609 |
| baseline_donchian_turtle | 1.67 / 41.7 / 7.37 / 48 / +1674 | 2.32 / 43.8 / 7.68 / 48 / +4171 | 2.04 / 37.5 / 8.84 / 48 / +3158 | 1.56 / 32.7 / 27.7 / 462 / +18004 | 1.57 / 33.4 / 27.7 / 515 / +23302 |
| baseline_atr_trail_breakout | 1.09 / 42.9 / 7.44 / 14 / +116 | 1.50 / 46.7 / 9.43 / 15 / +650 | 3.64 / 57.1 / 5.15 / 14 / +2815 | 1.47 / 44.3 / 15.7 / 97 / +3467 | 1.57 / 45.5 / 15.7 / 101 / +4326 |
| baseline_htf_fib_xau | 1.83 / 42.9 / 2.84 / 7 / +330 | 10.32 / 80.0 / 2.06 / 5 / +851 | 3.24 / 60.0 / 3.92 / 5 / +443 | 1.49 / 37.3 / 6.03 / 67 / +2029 | 1.63 / 39.5 / 6.03 / 81 / +3103 |
| baseline_htf_pullback_new | 1.37 / 53.2 / 7.62 / 77 / +1423 | 1.17 / 48.9 / 6.54 / 94 / +817 | 1.59 / 55.4 / 3.63 / 74 / +1761 **HP** | 1.27 / 50.5 / 8.95 / 588 / +10296 | 1.25 / 50.4 / 9.17 / 629 / +10759 |
| refined_donchian_exit_N8… | 1.92 / 45.8 / 7.37 / 48 / +2118 | 2.18 / 39.2 / 7.32 / 51 / +4068 | 2.24 / 40.8 / 7.60 / 49 / +3602 | 1.56 / 33.8 / 31.2 / 482 / +16686 | 1.55 / 34.4 / 31.2 / 540 / +20778 |
| refined_atr_pack_entry20… | 2.55 / 50.0 / 6.65 / 26 / +3268 | 1.92 / 47.2 / 9.45 / 36 / +3170 | 3.04 / 53.6 / 7.48 / 28 / +4775 | 1.62 / 44.3 / 28.3 / 237 / +14327 | 1.58 / 44.4 / 28.3 / 257 / +16236 |
| refined_htf_fib_best… | 0.98 / 32.5 / 6.62 / 40 / **−65** | 1.65 / 44.4 / 4.05 / 36 / +1294 | 1.36 / 40.0 / 6.64 / 40 / +803 | 1.14 / 35.4 / 20.9 / 387 / +3399 | 1.13 / 35.4 / 20.9 / 438 / +3761 |

*(Cells: PF / WR% / DD% / n / NP. **HP** = classic hard_pass.)*

---

## Stability verdict by lane

| Lane family | Call | Evidence |
|-------------|------|----------|
| **Donchian** (baseline + refined exit_N=8) | **Sign-stable** multi-year | PF>1 and +NP on 2023, 2024, 2025; still + on peeked 2026. Soft expectancy passes cluster on 2025 / halves / peek (mostly IS-friendly). Classic WR>55 remains a known mismatch for turtles. DD can be severe on long paths (develop ~28–31%). |
| **Vol gate sparse** | Signs hold; edge soft | Only multi-cell classic hard_pass lane (2023 pre-sample + peeked 2026). PF decays 2023→2025; develop_like ~1.03 washes edge. Not a promote case. |
| **ATR trail** (baseline + refined pack) | **Collapse 2023** | Baseline loses 2023 and 2024; refined loses 2023. 2025 soft story only — not robust multi-year breakout. |
| **HTF fib** baseline | Underpowered | n≈10–16 per year; high PF noise. |
| **HTF fib** refined | Mild IS; peek fails | Flat/negative on 2026_to_peek. |
| **HTF pullback** | PARK-consistent | Develop years soft +; **peek collapse**; sole IS hard_pass is h2_2025. |

---

## Promote ruling

| Gate | Status |
|------|--------|
| **PAPER_GO** | **no** |
| **LIVE_GO** | **no** |
| **promote** | **no** |
| Disposition | **RESEARCH_ONLY** |

Why (any one would suffice; all apply):

1. **2024–2025 are largely in-sample** for develop-selected frozen champs — not independent multi-year proof.
2. **2026_to_peek is contaminated** — re-score cannot mint virgin hard_pass.
3. **No sealed virgin window** with adequate bars after last peek (see prior virgin fire: `n_virgin_bars=2`, WAIT_DATA).
4. Only **3/72** classic hard_pass cells, and none on a clean sealed OOS package.
5. Multiplicity: same 8 configs already survived develop evals + refine + prior peeks; this matrix is autopsy, not a new confirmatory experiment.

**Never recommend `--live` from this multi-year pass.** Prefer PAPER_GO ≫ LIVE_GO only after a future sealed virgin hard_pass and skeptic LIVE_GO (extraordinary evidence) — this fire is neither.

---

## What would count as stronger evidence

1. **Primary:** Virgin H1 strictly after last peek (≥24 bars minimum; practically enough for n≥20 closed trades), single sealed pass of **frozen catalog only** — no retune, no grid.
2. **Already useful (not sufficient alone):** Pre-sample 2023 without refit — shows Donchian survives and ATR dies; research note only.
3. **Does not count:** Re-labeling 2025 as OOS; another pass on 2026_to_peek; soft_pass on IS halves; full_available PF stories; underpowered year cells (n≪20).

---

## Artifacts

| Path | Role |
|------|------|
| `results/xau_history_coverage.json` | Bars/year, `has_2023` |
| `results/xau_frozen_champions_catalog.json` | 8 frozen configs |
| `results/xau_frozen_multi_year_eval.json` | Full cell metrics + gates |
| `results/xau_frozen_multi_year_matrix.csv` | Compact PF/WR/DD/n/NP |
| `results/xau_frozen_multi_year_skeptic.md` | Hostile skeptic → promote=no |
| `results/xau_frozen_multi_year_summary.md` | This human summary |
| `results/xau_loop_status.md` | Loop status note |

---

## Safety checklist

- Offline research only; **no `--live`**, no orders
- No PAPER_GO / LIVE_GO from this fire
- Params only from frozen catalog; **no retune** on multi-year metrics
- IS vs peeked windows labeled explicitly (not re-labeled as OOS)
- Prefer future PAPER_GO over LIVE_GO if/when virgin hard_pass arrives
