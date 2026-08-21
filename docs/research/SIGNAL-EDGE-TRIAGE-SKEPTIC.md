# Signal-edge triage — skeptic addendum (CLEARS-FRICTION pair)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Parent** | `docs/research/SIGNAL-EDGE-TRIAGE.md` |
| **Subjects** | `ny_cash_liquidity_sweep`, `m5_zscore_tick_vol_exhaustion` |
| **Standing** | `promote=false`, `live_go=false` — **not** exit-grid ready; **not** a revival |

This note adversarially reviews the only two **CLEARS-FRICTION** rows from the triage. It does not retune, invert, reopen locks, or authorize a screen.

---

## Summary (read this first)

**Multiplicity first.** The triage measured **24** families. Under a rough extreme-value null for the maximum |t| across 24 independent tests,

\[
\mathbb{E}[\max |t|] \approx \sqrt{2\ln 24} \approx 2.52
\]

Observed CLEARS t-stats: **2.44** (`ny_cash_liquidity_sweep`) and **2.24** (`m5_zscore_tick_vol_exhaustion`). Both sit **at or below** what pure noise is expected to produce as the *maximum* across a sweep this wide. These are not survivors of a multiplicity correction — they are inside the null distribution of the max. That single line does more work than the other blockers combined, and it matches the workflow guardrail: a sweep of positives would be a bug; **two CLEARS out of 24 at null-expected t is the correct amount of nothing.**

**Arithmetic CLEARS stands; action does not.** Tool labels are correct in points. Do not revive, do not build an exit grid on these closed `search_id`s, do not promote.

**Dollar book (corrected):** `$/MT5 pt = point_size × contract_size × lots = 0.01 × 1 × 1 = $0.01` — not $0.02. Friction 80 pts = **$0.80** RT; edge 3883 pts = **$38.83**; ratio **48.5×** (unit-free, unchanged). An earlier draft doubled every dollar figure by misreading lock notes; CLEARS verdicts were never dollar-based.

---

## What the diagnostic actually said (reproduced)

Develop-only, `point=0.01`, `friction=80` MT5 pts. Canonical cost identity from the lock book: `point_size=0.01`, `contract_size=1.0`, `lots=1.0` → **$0.01 per MT5 point**. Friction 80 pts → **$0.80** RT. (Do not confuse `goal_monthly_pct: 0.20` with a dollar-per-point identity.)

| Family | Holdout | n | Best H | Mean (MT5 pts) | t | ≈ $/trade | Verdict |
|--------|---------|--:|-------:|---------------:|--:|----------:|---------|
| `ny_cash_liquidity_sweep` | `< 2026-06-01` | 80 | 50 | +3883 | +2.44 | **$38.83** | CLEARS-FRICTION |
| `m5_zscore_tick_vol_exhaustion` | `< 2026-07-01` | 92 | 20 | +3856 | +2.24 | **$38.56** | CLEARS-FRICTION |

Under the tool's rule (`best mean ≥ friction` and `t ≥ 2`), both labels are **arithmetically correct**. That is not the same as "ready for an exit grid" or "new freeze authorized."

---

## Falsifiers / blockers

### 1. Multiplicity — inside the null max (strongest)

See Summary. Expected max |t| across 24 ≈ **2.52**; observed **2.44** and **2.24**. Promote this above calendar/n/path arguments: even without those, the sweep does not elevate these t-stats above noise-max expectation.

### 2. Calendar is too short for a CLEARS claim

US100 M5 CSV span is roughly **2025-10-23 → 2026-08-18** (~10 months). Develop before June/July 2026 is mostly a **single winter–spring window**, not a multi-year book.

Year slices (same tool, no n≥50 filter):

| Family | 2025 n | 2025 verdict | 2026 n | 2026 verdict |
|--------|-------:|--------------|-------:|--------------|
| `ny_cash_liquidity_sweep` | 25 | **DEAD** (best t 1.12) | 55 | CLEARS-FRICTION |
| `m5_zscore_tick_vol_exhaustion` | 14 | **DEAD** (best t 0.63) | 78 | CLEARS-FRICTION |

Pooled CLEARS is **2026-driven**. 2025 alone does not clear. That is fragile.

### 3. Sample size + M5 horizon overlap

n ≈ **80–92** signals. Horizons 5…100 on M5 are highly overlapping paths (H50 ≈ 4h). t≈2.2–2.4 on autocorrelated forwards is a **weak** clearance even before multiplicity.

### 4. Already failed the exit-grid / book screens

These families are not virgin:

- `ny_cash_liquidity_sweep` — structure v3 screen: develop eligible **0**, holdout **0** (`results/us_index_session_structure_v3.md`).
- `m5_zscore_tick_vol_exhaustion` — v7: develop-eligible under the **1%/20% day book** was **0/13**; family showed develop PF interest then **holdout day % negative** (`results/us_index_session_v7.md`).

Signed-forward CLEARS can coexist with **SCREEN_FAIL under the frozen execution book**. Do **not** silently reopen those `search_id`s.

### 5. Post-search measurement, not freeze-before-peek

Signals were already designed/searched across US v1–v8 on this develop. Re-measuring them on the same develop is **archived classification**, not a pre-registered discovery. Quantitatively: this is the same 24-family sweep that sets the multiplicity debt in §1. A future thesis needs a **new** `family_id` / `search_id` with variables named before looking.

### 6. Point-unit honesty (corrected)

| Quantity | Wrong (earlier draft) | Correct |
|----------|----------------------|---------|
| $/MT5 point | $0.02 | **$0.01** (`point_size × contract_size × lots`) |
| Friction 80 pts | $1.60 | **$0.80** |
| Edge 3883 pts | ~$78 | **$38.83** |
| Edge / friction | ~48.5× | **48.5×** (unchanged — unit-free) |

`US_POINT=0.01` matches the locks. Friction 80 MT5 pts matches the slip+spread *point* book. The CLEARS test runs in **points**; the ratio is unit-free — **verdict unchanged**. The bug was only the dollar column, which must not be copied into a later sizing decision.

### 7. Median vs mean

Both families show **mean ≫ median** at the CLEARS horizon (e.g. sweep H50 mean 3883 vs median 2643; zscore H20 mean 3856 vs median 1562). Right-tail / path dependence risk — exit grids and time-flats can erase the mean.

---

## Verdict

| Claim | Skeptic call |
|-------|----------------|
| Tool label CLEARS-FRICTION | **Accepted** as arithmetic under stated rule |
| "Worth building an exit grid on the closed family" | **Rejected** (multiplicity + prior SCREEN_FAIL) |
| "Revive `ny_cash_liquidity_sweep` / `m5_zscore_tick_vol_exhaustion`" | **Forbidden** |
| "Evidence for a future NEW family_id after longer data / new freeze" | **Allowed as archive only** — not an authorization |

Standing remains: **`promote=false`, `live_go=false`.** No screen, null, lock edit, or charter edit from this note.

---

## Cleaner COST-BOUND pointer (not this pair)

EURUSD `mean_reversion` (H50 +11.75, t +4.14, friction 22, multi-year develop, regression-gated, found **before** this 24-family sweep) remains the **cleaner** COST-BOUND case if a future **new** cheaper-execution / different-TF thesis is grilled. It does not carry this sweep's multiplicity debt. That is still **not** a revival of the closed EURUSD screen.

**Honest prior for any such grill:** edge ≈ 11.7 pts vs 22 pts friction; even at zero slippage ≈ 11.7 vs ~12 — break-even on paper. A new family must earn its keep on the **cost / execution** side (limits, measured slip), not by subsetting the 7,819 signals. If it cannot clear friction on paper before a screen is written, that is a cheaper SCREEN_FAIL than running one.
