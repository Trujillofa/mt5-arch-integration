# XAU retrain + walk-forward

**Sources:** `results/xau_regime_analysis.json`, `results/xau_train_only_retrain.json`, `results/xau_walkforward.json`, `results/xau_oos_holdout.json`  
**Split (holdout / retrain):** `2026-01-02 18:18:00+00:00`  
**Strategy family:** `bb_rsi` (long-only, EMA200 trend filter available)

---

## Safety (no live)

**No live trading.** Evidence does **not** support enabling live or `--live`.

| Gate | Result |
|------|--------|
| Holdout OOS gates | `oos_gates_pass=false` (PF 0.59, WR 42.9%, n=7) |
| Train-only retrain OOS gates | `oos_gates_pass=false` (PF 0.141, WR 9.1%, n=11) |
| Walk-forward fold pass rate | **0/4** (`fold_pass_rate=0.0`) |
| Retrain candidate adopted | No — `strategy_params` unchanged |

Use dry-run / offline analysis only. Do not promote params to production.

---

## Regime shift findings

Clear train→OOS regime change on the fixed split (`xau_regime_analysis.json` / phase payload).

| Feature | Train | OOS | Ratio / delta |
|---------|------:|----:|---------------|
| Bars | 8132 | 3505 | — |
| ATR mean | 10.17 | 24.77 | **~2.44×** |
| Return std | 0.00224 | 0.00415 | **~1.85×** |
| BB width mean | 0.014 | 0.025 | **~1.76×** |
| Frac close > EMA200 | 0.687 | 0.482 | **Δ −0.205** |
| Long signal bars | 59 | 16 | lower signal rate |

**Fixed baseline `bb_rsi` metrics on same split:**

| | n | PF | WR | Net | Max DD% |
|--|--:|---:|---:|----:|--------:|
| Train | 40 | 1.84 | 62.5% | +1256 | 3.56 |
| OOS | 7 | 0.59 | 42.9% | −136 | 2.76 |

**Interpretation:** Higher volatility, wider bands, and less time above EMA200 coincide with collapse of the fixed-param edge. OOS sample is thin (7 trades), so point estimates are noisy but directionally negative.

---

## Train-only retrain vs baseline

**Search:** 324-point train-only grid (~5.9 s). Selection on train gates / train metrics only; OOS evaluated after.  
**Winner (train):** `rsi_buy=30`, `rsi_sell=60`, `sl/tp=1.0/1.5`, `bb_lo`, `cooldown=1`, `require_uptrend=True`.  
**Result:** `oos_gates_pass=false` — **no candidate**; strategy params left at baseline.

| Set | n | PF | WR | Net | Max DD% |
|-----|--:|---:|---:|----:|--------:|
| **Retrain train** | 45 | **1.894** | 55.6% | +1839 | 3.60 |
| **Retrain OOS** | 11 | **0.141** | **9.1%** | **−714** | **7.14** |
| Baseline train | 40 | 1.837 | 62.5% | +1256 | 3.56 |
| Baseline OOS | 7 | 0.588 | 42.9% | −136 | 2.76 |

**Notes:**
- Train improved slightly on PF / net (PF 1.837 → 1.894; n 40 → 45).
- OOS worsened sharply vs baseline (PF 0.59 → 0.14; WR 43% → 9%; net −136 → −714; DD 2.76% → 7.14%).
- Classic overfit: train-only grid search did not transfer; `n_passers_train=20` still failed OOS gates.

---

## Walk-forward aggregate

**Method:** Expanding train + 4 equal-bar OOS from `2025-01-01` (`scripts/xau_walkforward.py`).  
**Grid (train-only):** `rsi_buy` ∈ {25,30,35}; `sl/tp` ∈ {(1.0,1.5),(1.5,2.0)}; `require_uptrend` T/F (12 points).  
**Selection:** pass train gates, then max train net profit. Baseline = fixed `strategy_params` on same folds. No fit on OOS.

### Aggregate OOS (re-optimized per fold)

| Metric | WF | Fixed baseline |
|--------|---:|---------------:|
| Sum OOS net profit | **+634.5** | **+823.8** |
| Mean PF | 1.23 | 2.71 |
| Mean WR | 56% | 61% |
| Total trades | 75 | 36 |
| Fold pass rate | **0/4** | **0/4** |
| Min OOS DD% | 2.64 | 1.38 |

**vs baseline:** WF underperforms by **−189 NP** and **−1.48 mean PF** (`wf_better_on_np=false`).

### Per-fold OOS (WF chosen params)

| Fold | OOS window (approx) | n | PF | WR | Net | Gates |
|-----:|---------------------|--:|---:|---:|-----:|:-----:|
| 1 | 2025-01 → 2025-05 | 36 | 1.28 | 61% | +364 | fail |
| 2 | 2025-05 → 2025-10 | 25 | 1.14 | 48% | +170 | fail |
| 3 | 2025-10 → 2026-03 | 9 | 2.04 | 67% | +253 | fail |
| 4 | 2026-03 → 2026-08 | 5 | 0.45 | 40% | −153 | fail |

Fold 4 (most recent, post-regime) is negative and thin; holdout 2026 OOS aligns with that weakness.

---

## Go / no-go gates

| Criterion | Threshold / rule | Observed | Pass? |
|-----------|------------------|----------|:-----:|
| Holdout OOS gates | PF≥1.5, WR≥55%, DD≤10% | PF 0.59, WR 43%, n=7 | **No** |
| Retrain OOS gates | same | PF 0.14, WR 9%, n=11 | **No** |
| Retrain OOS sample | n≥15 for promotion path | n=11 | **No** |
| WF fold pass rate | ≥50% | 0/4 (0%) | **No** |
| WF beats fixed baseline | sum NP / mean PF | −189 NP, −1.48 PF | **No** |
| Live / `--live` | requires clear multi-gate pass | fails all above | **No** |

### Decision

**NO-GO for live.**  
**NO-GO for param thrashing.** Retrain OOS fails; WF fold pass rate is 0%; recent/holdout OOS trades are thin and negative. Stay dry-only; redesign or pivot path, not more `bb_rsi` grid search on the same features.

---

## Recommended next steps (ordered)

1. **Stay dry-only** — do not enable live, do not change production `strategy_params` from this retrain, do not run further large param grids on the same `bb_rsi` setup expecting OOS rescue.
2. **Treat 2026 regime as structural** — ATR ~2.4×, return vol ~1.85×, less time above EMA200; mean-reversion-long-on-bb_lo is misaligned. Document this as a hard invalidation for the current edge until a new design is validated.
3. **Strategy redesign (preferred over retune)** — e.g. volatility-normalized entries, regime filter (trade only when ATR / BB width in train-like bands), or flip/suppress longs when frac>EMA200 is weak; re-validate with holdout + WF before any paper path.
4. **HTF Fib path** — prioritize existing HTF Fib offline/dry work (`htf_fib_*` results) as an alternate XAU thesis rather than squeezing `bb_rsi` further.
5. **If redesign later passes gates** — still no live: paper/dry loop + MT5 Python bridge for a real dry order path only after OOS n≥15, OOS gates pass, and WF fold pass rate mostly positive.
6. **Never promote with `--live` from this report** — current evidence is insufficient.

---

*Generated from phase payloads REGIME_OK / RETRAIN_OK / WF_OK and the four result JSON files. Numbers only from those sources.*
