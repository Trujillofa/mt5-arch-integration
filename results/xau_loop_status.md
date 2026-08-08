# XAU offline loop status

## 2026-08-08 — null / max-stat test (decisive for bb_rsi family)

After measured costs flipped walk-forward negative, the remaining question was
whether the develop-window gate-passers were market signal or search artifacts.
`scripts/xau_null_maxstat.py` scored the full ~1205-config grid (no early exit)
on develop bars with saved costs, then re-ran the same search on 40
return-shuffled price paths.

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | measured spread; commission/slippage still 0 |
| **grid** | 1205 configs (max_n=1200, seed=42 + 5 seeds) |
| **real max PF (n≥20)** | 2.242 · n_passers **19** · early-exit eligible 10 |
| **baseline replay** | PF 1.6713 · n=42 (still clears gates alone) |
| **null (40 trials)** | max PF p50 **≈3.0** · n_passers p50 **≈22** (often *more* passers than real) |
| **p(null ≥ real)** | p_max_pf **0.854** · p_n_passers **0.707** |
| **disposition** | **KILL_BB_RSI_LINE** |
| **live_go** | **false** |
| **promote** | **no** |

The gates measured the search, not the market. Do **not** tune `bb_rsi` further,
do not cross-instrument this family, do not promote. Artifacts:
`results/xau_null_maxstat.json`, `results/xau_null_maxstat.md`.

Commission figure from Vantage is still useful as cost floor for *other* lanes
(e.g. re-costed Donchian), not for rescuing this one.

---

## 2026-08-08 — transaction costs added (out of band, not a research fire)

The backtest was frictionless. `MqlRates.spread` was always available and the old
`Scripts/ExportXauHistory.mq5` discarded it; `Mt5ArchBridge.mq5` v1.21 now dumps it.

| Field | Value |
|-------|--------|
| **source** | Vantage live terminal (27496181), one-shot bridge dump, 129133 rows |
| **spread** | XAUUSD H1 median **18 pts = $0.18** round trip · p90 $0.21 · max $0.50 |
| **zero-spread bars** | H1 4.4% / M15 2.0% — broker backfill gaps, filled with the median (0 would read as free trading) |
| **data** | H1 29133 bars 2021-09-03 → 2026-08-07 (was 29151, re-exported) |
| **baseline** | same params; PF **1.7456 → 1.6713**, net $1299 → $1188, n=42 (develop only) |
| **walk-forward** | retrained OOS **flips negative**: NP +122 → **−282**, meanPF 1.318 → **0.790**, pass_rate 0% |
| **commission/slippage** | **not measured** — MT5 exposes them only on executed deals. Left at 0; see sensitivity |
| **live_go** | **false** (unchanged) |
| **promote** | **no** (unchanged) |

Sensitivity on the develop-window baseline (measured spread already charged):

| Scenario | PF | Net |
|---|---|---|
| frictionless | 1.7456 | $1299 |
| measured spread only | 1.6713 | $1188 |
| + $3/lot | 1.6372 | $1139 |
| + $3/lot + 10pt slip | 1.5548 | $1006 |
| + $5/lot + 20pt slip | **1.4264** | $795 — below gate |

The baseline survives measured spread; it does not survive spread + $5/lot + 20pt.
Commission for this account still needs the broker contract spec.

---

## 2026-08-06 — baseline protocol correction (out of band, not a research fire)

`strategy_params.json` was re-fitted because its recorded metrics no longer reproduced
(claimed PF 1.7256 / 50 trades; replayed PF 1.378 / 124 trades on the shipped CSV — the
params predated a CSV extension and carried no fit window).

| Field | Value |
|-------|--------|
| **cause** | params file recorded no fit window; CSV grew underneath it |
| **first refit** | unbounded (2021-09-01 → 2026-08-06) — **violated** `holdout_rule`, discarded |
| **shipped refit** | selection window `time < 2026-01-01` (25626 H1 bars); holdout sealed |
| **baseline now** | PF 1.7456 · WR 59.52 · DD 3.81 · n=42 (develop only, in-sample) |
| **guard** | `backtest.py` bounds selection at `holdout_start` from `xau_holdout_lock.json`; `--unbounded` warns |
| **downstream** | `xau_regime_analysis` / `xau_walkforward` / `xau_train_only_retrain` re-run against the corrected baseline |
| **live_go** | **false** (unchanged) |
| **promote** | **no** (unchanged) — baseline OOS samples are tiny: 12–13 trades, 3 long signals in 2026 |

2026 was already labeled `2026_to_peek` (peeked, diagnostic only) before this correction, so
the re-runs consume no fresh holdout. The sealed virgin path is unchanged and still WAIT_DATA.

---

| Field | Value |
|-------|--------|
| **timestamp_utc** | 2026-08-06 (multi-year fire) |
| **fire** | frozen multi-year matrix (DATA → EVAL → SKEPTIC → SUMMARY) |
| **action_taken** | Evaluated 8 frozen catalog configs on 9 windows (72 cells); no retune; skeptic **promote=no** |
| **coverage** | 2023:5894 · 2024:5935 · 2025:5911 · 2026:3525 H1 bars (`has_2023=true`) |
| **eval** | years 2023/2024/2025/2026_to_peek + develop_like/full/halves; **hard_pass 3/72** |
| **stability** | Donchian sign-stable (+NP/PF>1) across years incl. pre-sample 2023; atr_trail collapses 2023 |
| **window labels** | 2024–25 largely **IS**; 2026_to_peek **peeked** (diagnostic only); 2023 pre-sample stress |
| **live_go** | **false** |
| **stop_reason** | **RESEARCH_ONLY** — multi-year autopsy complete; promote=no; virgin frontier still WAIT_DATA |
| **next_step** | Idle on virgin: when `n_virgin_bars ≥ 24` after last peek, single sealed virgin eval of frozen 8 only (no retune). Do **not** re-mine 2026_to_peek or re-label IS years as OOS. Never `--live` unless skeptic LIVE_GO. |

## Phase checklist this fire

| Phase | Ran | Note |
|-------|:---:|------|
| DATA | true | 2023:5894 2024:5935 2025:5911 2026:3525 |
| EVAL | true | years available: 2023,2024,2025,2026_to_peek (+ develop_like, full, h2_2024, h1_2025, h2_2025); hard_pass cells: 3/72 |
| SKEPTIC | true | Donchian sign-stable; atr_trail collapses 2023; 2024–25 IS + 2026 peeked — promote=no |
| SUMMARY | true | `results/xau_frozen_multi_year_summary.md` |

## Artifacts written / updated this fire

| Path | Role |
|------|------|
| `results/xau_history_coverage.json` | Bars/year coverage |
| `results/xau_frozen_multi_year_eval.json` | Full cell metrics |
| `results/xau_frozen_multi_year_matrix.csv` | Compact matrix |
| `results/xau_frozen_multi_year_skeptic.md` | Hostile skeptic → promote=no |
| `results/xau_frozen_multi_year_summary.md` | Human summary + per-lane×year tables |
| `results/xau_loop_status.md` | This note |

## Prior context (unchanged)

- Catalog: 8 frozen configs (baseline + refined_develop)
- Virgin frontier still insufficient (`n_virgin_bars=2` at last virgin fire) → WAIT_DATA for sealed promote path
- Develop program priorities exhausted; PARK vol_gate / htf_pullback; KILL=0

## Safety checklist

- No `--live`, no orders
- No paper/live GO from this fire
- Multi-year matrix is diagnostic only — IS and peeked windows not re-labeled as independent OOS
- Prefer PAPER_GO ≫ LIVE_GO on any future virgin hard_pass

## Stop-condition check

1. Live GO virgin hard_pass → **false**
2. Multi-year offline autopsy complete → **true** (this fire)
3. Waiting on virgin future data → **still true** (promote path unchanged)
4. Task expired → false

**Disposition this fire:** **RESEARCH_ONLY / promote=no** (Donchian multi-year sign-stable including 2023; ATR collapses 2023; no PAPER_GO/LIVE_GO; never `--live`)
