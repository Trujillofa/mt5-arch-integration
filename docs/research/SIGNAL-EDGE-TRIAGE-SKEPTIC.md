# Signal-edge triage — skeptic addendum (CLEARS-FRICTION pair)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Parent** | `docs/research/SIGNAL-EDGE-TRIAGE.md` @ `e731433` |
| **Subjects** | `ny_cash_liquidity_sweep`, `m5_zscore_tick_vol_exhaustion` |
| **Standing** | `promote=false`, `live_go=false` — **not** exit-grid ready; **not** a revival |

This note adversarially reviews the only two **CLEARS-FRICTION** rows from the triage. It does not retune, invert, reopen locks, or authorize a screen.

---

## What the diagnostic actually said (reproduced)

Develop-only, `point=0.01`, `friction=80` MT5 pts (lock book: 10 pt slip/side + spread; lock note ≈ **$0.02 / MT5 pt** → friction ≈ **$1.60** RT at 1 lot):

| Family | Holdout | n | Best H | Mean (MT5 pts) | t | ≈ $/trade | Verdict |
|--------|---------|--:|-------:|---------------:|--:|----------:|---------|
| `ny_cash_liquidity_sweep` | `< 2026-06-01` | 80 | 50 | +3883 | +2.44 | ~$78 | CLEARS-FRICTION |
| `m5_zscore_tick_vol_exhaustion` | `< 2026-07-01` | 92 | 20 | +3856 | +2.24 | ~$77 | CLEARS-FRICTION |

Under the tool's rule (`best mean ≥ friction` and `t ≥ 2`), both labels are **arithmetically correct**. That is not the same as "ready for an exit grid" or "new freeze authorized."

---

## Falsifiers / blockers

### 1. Calendar is too short for a CLEARS claim

US100 M5 CSV span is roughly **2025-10-23 → 2026-08-18** (~10 months). Develop before June/July 2026 is mostly a **single winter–spring window**, not a multi-year book.

Year slices (same tool, no n≥50 filter):

| Family | 2025 n | 2025 verdict | 2026 n | 2026 verdict |
|--------|-------:|--------------|-------:|--------------|
| `ny_cash_liquidity_sweep` | 25 | **DEAD** (best t 1.12) | 55 | CLEARS-FRICTION |
| `m5_zscore_tick_vol_exhaustion` | 14 | **DEAD** (best t 0.63) | 78 | CLEARS-FRICTION |

Pooled CLEARS is **2026-driven**. 2025 alone does not clear. That is fragile.

### 2. Sample size + M5 horizon overlap

n ≈ **80–92** signals. Horizons 5…100 on M5 are highly overlapping paths (H50 ≈ 4h). t≈2.2–2.4 on autocorrelated forwards is a **weak** clearance, not a robust edge proof.

### 3. Already failed the exit-grid / book screens

These families are not virgin:

- `ny_cash_liquidity_sweep` — structure v3 screen: develop eligible **0**, holdout **0** (`results/us_index_session_structure_v3.md`).
- `m5_zscore_tick_vol_exhaustion` — v7: develop-eligible under the **1%/20% day book** was **0/13**; family showed develop PF interest then **holdout day % negative** (`results/us_index_session_v7.md`).

So: signed-forward CLEARS can coexist with **SCREEN_FAIL under the frozen execution book**. That is exactly why the diagnostic exists — and why CLEARS here must **not** silently reopen those `search_id`s.

### 4. Post-search measurement, not freeze-before-peek

Signals were already designed/searched across US v1–v8 on this develop. Re-measuring them on the same develop is **archived classification**, not a pre-registered discovery. A future thesis needs a **new** `family_id` / `search_id` with variables named before looking.

### 5. Point-unit honesty (pass, with caveat)

`US_POINT=0.01` matches the locks (`point_size: 0.01`). Friction 80 MT5 pts matches the slip+spread book shape. Dollar translation from the lock's "10 pt = $0.20" note is consistent (~$1.60 friction vs ~$77 mean edge). **Units are not the bug.** Fragility of window/n/prior SCREEN_FAIL is.

### 6. Median vs mean

Both families show **mean ≫ median** at the CLEARS horizon (e.g. sweep H50 mean 3883 vs median 2643; zscore H20 mean 3856 vs median 1562). Right-tail / path dependence risk — exit grids and time-flats can erase the mean.

---

## Verdict

| Claim | Skeptic call |
|-------|----------------|
| Tool label CLEARS-FRICTION | **Accepted** as arithmetic under stated rule |
| "Worth building an exit grid on the closed family" | **Rejected** |
| "Revive `ny_cash_liquidity_sweep` / `m5_zscore_tick_vol_exhaustion`" | **Forbidden** |
| "Evidence for a future NEW family_id after longer data / new freeze" | **Allowed as archive only** — not an authorization |

Standing remains: **`promote=false`, `live_go=false`.** No screen, null, lock edit, or charter edit from this note.

---

## Cleaner COST-BOUND pointer (not this pair)

EURUSD `mean_reversion` (H50 +11.75, t +4.14, friction 22, multi-year develop, regression-gated) remains the **cleaner** COST-BOUND case if a future **new** cheaper-execution / different-TF thesis is grilled. That is still **not** a revival of the closed EURUSD screen.
