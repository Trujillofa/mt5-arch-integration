# XAU offline loop status

## 2026-08-10 — server_hour v2 SCREEN_FAIL · RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS

| Field | Value |
|-------|--------|
| **next_step** | **`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |
| **v2 charter** | SHA `26ff7532…` · registry **SCREEN_FAIL** / `ZERO_PRIMARY_PASSERS` |
| **real grid (develop)** | PF **0.8511** · NP **−5052.80** · DD **58.54%** · n **1114** · primary passers **0** |
| **p_n_passers_implied** | **1.0** (arithmetic; nulls not needed) |
| **r1_burned** | **false** |
| **protocol rule** | Real primary passers == 0 → **SCREEN_FAIL without null trials** |
| **next family** | New `family_id` only; freeze before grid peek; null only if ≥1 primary passer |

Do not run: r1, walk-forward, holdout eval, retune, paper, live on closed freezes.

---

## 2026-08-10 — protocol v2.2.1 preregistration + enforcement (still no r1)

| Field | Value |
|-------|--------|
| **v1 server_hour charter** | Registry **SUPERSEDED** (SHA `6b5811ee…`) — preregistered close-return algorithm ≠ v2.2 runtime |
| **v2 freeze** | `results/xau_charters/2026-08-10_server_hour_window_flat_v2.json` · method **`within_day_ohlc_increment_rotate_v1`** · full algorithm + k-domain + OHLC invariants |
| **session null policy** | Canonical method required; `forbidden_methods` enforced; noncanonical rejected |
| **registry integrity** | Malformed JSONL → fail closed; terminal dispositions monotonic |
| **dirty tree** | Sealed / strict-charter refuse dirty tracked protocol/family/cost files |
| **r1** | **not burned** |
| **next** | External review of v2 freeze, then optional sealed r1 on **v2 only** |
| **promote / live_go** | no / false |

---

## 2026-08-10 — protocol v2.2 correction (still do not burn r1)

Review of v2.1 found OHLC-inconsistent within-day null and forced non-identity k.

| Field | Value |
|-------|--------|
| **null v2.2** | Rotate **complete normalized OHLC increments**; k∈{0..m−1} **includes identity**; open/prev and TR/ref multisets preserved; develop gap bp no longer inflated |
| **TOD v1 freeze** | Restored **byte-for-byte** (SHA `e7cd953f…`); invalidation **only** in `results/xau_charter_disposition_registry.jsonl` |
| **strict paths** | `--charter` runs `validate_charter` + registry runnable check; costs keys must exist on both sides |
| **r1** | **not burned** |
| **next** | Re-review then optional sealed `server_hour_window_flat` |
| **promote / live_go** | no / false |

---

## 2026-08-10 — protocol v2.1 correction wave (do not burn r1)

Review blocked Phase 0 on four points; correction shipped without running sealed r1.

| Field | Value |
|-------|--------|
| **TOD v1** | `PROTOCOL_NULL_INVALID` / exploratory `SCREEN_FAIL` — see `results/xau_tod_v1_disposition.md`. **r1 not burned.** |
| **Null fix** | New method `within_day_return_rotate` (per-day return rotation + price rebase). `day_block_shuffle` marked session-invalid. |
| **Clock** | No London–NY claim; superseding family is **server-hour labels only**. |
| **Strict charter** | Family id / null method / n_trials / costs equality; sealed cycle blocks fixture skips. Slip sensitivity rows generated in report. |
| **Superseding freeze** | `results/xau_charters/2026-08-10_server_hour_window_flat_v1.json` + `scripts/xau_family_server_hour_window_flat.py` |
| **PR #1 honesty** | Protocol commits landed on the same branch as draft PR #1 head — **scope expanded**; review as such (not a clean research-only PR). |
| **next_step** | Optional sealed run of `server_hour_window_flat` when ready (still not automatic). promote=no / live_go=false. |

---

## 2026-08-10 — protocol v2 Phase 0 (harden + freeze TOD charter)

Owner-required protocol hardening **before** any next sealed thesis run.

| Field | Value |
|-------|--------|
| **charters** | Immutable under `results/xau_charters/YYYY-MM-DD_<family>_vN.json` (refuse overwrite). Legacy `xau_next_design_charter.json` (`prior_day_high_break`) **not** overwritten. |
| **gates** | From frozen charter when `--charter` passed (fixes prior soft-gate provenance mismatch). |
| **n_null floor** | ≥**199** (prefer **999** for 0–1 knobs); charter freezes count. |
| **null methods** | `global_return_shuffle` \| `day_block_shuffle` \| `circular_day_shift` + invariants. |
| **costs wording** | Account-matched spread+commission only; **slip unmeasured**, **swap unmodeled** → intraday-flat required (v2). |
| **sealed cycle** | `scripts/xau_sealed_family_cycle.py` + attempt ledger `results/xau_family_attempts.jsonl` |
| **next frozen family** | **`tod_london_ny_flat`** zero-knob session thesis — charter only, **sealed run not yet executed** |
| **candidates** | Multi-instrument **deferred**; EMA/H4 pullback **removed** (dead htf_pullback overlap) |
| **PR #1** | **Do not expand scope** until current draft is reviewed |
| **next_step** | Run sealed cycle for TOD when ready: `python3 scripts/xau_sealed_family_cycle.py --charter results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json --family tod_london_ny_flat --run-id r1` |
| **promote / live_go** | **no / false** |

Docs: `docs/research/XAU-FAMILY-PROTOCOL-V2.md`.

---

## 2026-08-10 — cost model matched to live Standard STP

Live account confirmed: **MT5 27496181 · Standard STP · 500:1 · VantageMarkets-Live 5**.

| Field | Value |
|-------|--------|
| **commission** | **$0** (Standard STP — no ticket commission) |
| **spread** | measured from this terminal (H1 median 18 pts) |
| **research default** | `results/xau_research_costs.json` → `commission_per_lot=0`, `account_type=STANDARD_STP` |
| **RAW $3 / PRO $1.50** | stress alternatives only (other account types), not this login |
| **correction** | 2026-08-08 resume-edge had defaulted to RAW $3 before account type was known — **over-costed** relative to 27496181 |
| **strategy disposition** | unchanged: dead families stay dead; `RESEARCH_IDLE_PENDING_NEW_THESIS` |
| **promote / live_go** | **no / false** |

Null kills already run under commission 0 or 3 still stand as process outcomes; any *new* family search should use Standard STP costs (spread + commission 0). Re-running old nulls under RAW was a conservative stress, not live-matched.

---

## 2026-08-08 — resume-edge: RAW $3 costs + prior_day_high_break null KILL

Consolidated status after the **xau-resume-edge** fire (Vantage commission bake-in →
next-design charter → family null scaffold → first low-knob family → full null).

| Field | Value |
|-------|--------|
| **cost update** | Vantage research default **RAW ECN $3.00 / side / lot** (`commission_per_lot=3.0`); PRO $1.50 sensitivity only. Source: `results/xau_research_costs.json`. RT commission = `2 * 3.0 * lots` ($0.06 @ 0.01 lot, $6 @ 1.0 lot) + measured H1 spread. Slippage still 0. |
| **next design family** | **`prior_day_high_break`** (charter-frozen; 1 free knob `sl_atr` ∈ {1.0, 1.5, 2.0}; cardinality **3**) |
| **null disposition** | **`KILL_PRIOR_DAY_HIGH_BREAK`** — p_max_pf **0.463** · p_n_passers **1.000** · real max PF (n≥20) **1.077** · soft passers **0** (null can match/beat) |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **`RESEARCH_IDLE_PENDING_NEW_THESIS`** — null **KILL** (not PASS). Do **not** run costed walk-forward for this family. Do **not** retune knobs / free hours / frictionless rescue. A new family requires a **new charter freeze** (`NEXT_FAMILY` only after that freeze). |

Dead lines (do not revive): `bb_rsi`, `Donchian`/`turtle`, `prior_day_high_break`.

Key artifacts: `results/xau_research_costs.json`, `results/xau_cost_update_vantage.md`,
`results/xau_next_design_charter.{json,md}`, `scripts/xau_null_core.py`,
`scripts/xau_family_null_maxstat.py`, `scripts/xau_family_prior_day_high_break.py`,
`results/xau_prior_day_high_break_null_maxstat.{json,md}`,
`results/xau_prior_day_high_break_null_skeptic.md`,
`.grok/workflows/xau-resume-edge.rhai`.

---

## 2026-08-08 — prior_day_high_break null / max-stat (charter family KILL)

After `KILL_BB_RSI_LINE` and `KILL_DONCHIAN_LINE`, the frozen next-design charter
(`results/xau_next_design_charter.json`) pre-registered `prior_day_high_break`
(3-config grid: `sl_atr` ∈ {1.0, 1.5, 2.0}). Develop grid was scored under RAW
costs; then `scripts/xau_family_null_maxstat.py --family prior_day_high_break`
ran the full null max-stat protocol (no early exit).

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | spread_col=spread, point_size=0.01, commission_per_lot=**3.0** (RAW ECN), slippage=0 |
| **grid** | **3** configs (charter search_cardinality; full enumerate) |
| **real max PF (n≥20)** | **1.0773** · n_passers_soft **0** · n_passers_classic **0** |
| **null (40 trials)** | max PF p50 **≈1.05** · null max **1.31** · n_passers_soft p50 **0** (null max soft passers **2**) |
| **p(null ≥ real)** | p_max_pf **0.463** · p_n_passers **1.000** · p_n_passers_classic **1.000** |
| **disposition** | **KILL_PRIOR_DAY_HIGH_BREAK** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **RESEARCH_IDLE** — do **not** retune, widen knobs, free hours/tp_rr, or re-run frictionless |

KILL is a valid success of the scientific process under the charter kill rules.
Real best-of-grid (PF≈1.08, zero soft passers under PF≥1.2 / n≥20 / NP>0) sits
inside the return-shuffle null; null paths reach max PF **1.31** and up to **2**
soft passers. Do **not** launder KILL into walk-forward or PASS_KEEP_FROZEN.
A new family requires a **new** charter freeze (new family_id).

Artifacts: `results/xau_prior_day_high_break_null_maxstat.json`,
`results/xau_prior_day_high_break_null_maxstat.md`,
`results/xau_prior_day_high_break_null_skeptic.md`,
`results/xau_prior_day_high_break_develop_grid.json`,
`scripts/xau_family_null_maxstat.py`, `scripts/xau_family_prior_day_high_break.py`,
`results/xau_next_design_charter.json`.

---

## 2026-08-08 — Charter Option B adopted

**Charter:** Option B (explicit dual-layer) adopted — see [`docs/CHARTER-RESEARCH-LAYER.md`](../docs/CHARTER-RESEARCH-LAYER.md) and [`results/xau_charter_adopted.md`](xau_charter_adopted.md).

Strategy disposition is **unchanged** by charter adoption:

| Field | Value |
|-------|--------|
| **next_step** | **RESEARCH_IDLE** |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |

Merge under dual-layer boundaries ≠ promote. No live orders without explicit consent.

---

## 2026-08-08 — Donchian null / max-stat (decisive for turtle / Donchian family)

After costed multi-year left Donchian as the only sign-stable lane under spread,
`scripts/xau_donchian_null_maxstat.py` scored the full ~1201-config Donchian grid
(no early exit) on develop bars with saved costs, then re-ran the same search on
40 return-shuffled price paths.

| Field | Value |
|-------|--------|
| **window** | develop only, 25582 H1 bars (`time < 2026-01-01`), holdout sealed |
| **costs** | measured spread; commission/slippage still 0 |
| **grid** | 1201 configs (max_n=1200, seed=42, frozen_prepended=2) |
| **real max PF (n≥20)** | 1.9955 · n_passers_soft **19** · n_passers_classic 1 |
| **null (40 trials)** | max PF p50 **≈1.53** · null max **3.19** · n_passers_soft p50 **0** (null can put up to 308) |
| **p(null ≥ real)** | p_max_pf **0.195** · p_n_passers **0.293** · p_n_passers_classic **0.341** |
| **disposition** | **KILL_DONCHIAN_LINE** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **RESEARCH_IDLE** (strategy-edge); virgin-only `WAIT_DATA` for process hygiene — not permission to mine Donchian on virgin |

The gates measured the search, not the market. Do **not** retune Donchian/turtle
champions, do not cross-instrument this family, do not promote, do not launder
KILL into PASS_KEEP_FROZEN. bb_rsi already dead; Donchian now dead. No remaining
interesting strategy lane from the frozen catalog for further edge research.

Artifacts: `results/xau_donchian_null_maxstat.json`, `results/xau_donchian_null_maxstat.md`,
`results/xau_donchian_null_skeptic.md`, `scripts/xau_donchian_null_maxstat.py`,
`.grok/workflows/xau-donchian-null-maxstat.rhai`.

---

## 2026-08-08 — costed frozen multi-year after bb_rsi kill

After `KILL_BB_RSI_LINE`, lane sims were wired to charge the same round-trip costs as
`backtest.simulate`, then the frozen 8×9 multi-year matrix was re-scored (no retune).

| Field | Value |
|-------|--------|
| **fire** | costed frozen multi-year (wire costs → EVAL → SKEPTIC) |
| **context** | bb_rsi null-killed; prior multi-year was frictionless / unfalsifiable |
| **costs** | `spread_col=spread`, `point_size=0.01`, `commission_per_lot=0`, `slippage_points=0` (measured H1 median ~18 pts / ~$0.18 RT; commission/slip still unmeasured) |
| **catalog** | 8 frozen configs × 9 windows = 72 cells; params from `xau_frozen_champions_catalog.json` only |
| **hard_pass** | classic **2/72** (was 3/72 frictionless); soft expectancy **13/72** (unchanged count) |
| **lost under costs** | vol_gate 2023 classic hard_pass (PF 1.51→1.384); pullback 2023 **sign flip**; vol_gate `develop_like` **dies** (PF<1 / NP−) |
| **sign-stable 2023–2025 under spread** | **Donchian only** (baseline + refined exit_N8); ATR still collapses 2023; fib thin-n / peek weak |
| **disposition** | **RESEARCH_ONLY** |
| **live_go** | **false** |
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **next_step** | **Donchian null / max-stat** (spread-costed, develop-only, mirror bb_rsi null protocol). Fail → KILL_DONCHIAN_LINE / RESEARCH_IDLE; pass → keep frozen for virgin-only future eval (still promote=no until sealed virgin hard_pass). |

Do **not** revive bb_rsi, re-mine 2026_to_peek, re-label IS years as OOS, or promote from this matrix.
Costs reduced gate hits; they did not create independence.

### Artifacts this fire

| Path | Role |
|------|------|
| `results/xau_post_kill_plan.md` | Wire + re-eval plan |
| `results/xau_frozen_multi_year_eval.json` | Costed cells + meta.costs |
| `results/xau_frozen_multi_year_matrix.csv` | Compact costed matrix |
| `results/xau_frozen_multi_year_costed_skeptic.md` | Hostile skeptic → promote=no; next Donchian null |
| `results/xau_post_kill_summary.md` | Executive summary (kill + costed re-eval + next) |
| `results/xau_loop_status.md` | This note |

Code (left uncommitted for parent): `scripts/xau_lane_deep_opt.py`, `scripts/xau_frozen_multi_year_eval.py` (+ eval json/csv).

---

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
