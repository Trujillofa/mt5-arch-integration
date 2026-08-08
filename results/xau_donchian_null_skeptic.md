# XAU Donchian Null / Max-Stat — Hostile Skeptic

**Date:** 2026-08-08  
**Stance:** Fail closed. Safety: `promote=no` unless the impossible bar is cleared (it will not be).  
**Pipeline phase:** Decisive offline null test of the last multi-year survivor under measured spread. No retune. No cross-instrument. No `--live`.

**Artifacts reviewed:**

| Path | Role |
|------|------|
| `results/xau_donchian_null_maxstat.md` | Protocol, real grid, null table, disposition |
| `results/xau_donchian_null_maxstat.json` | Machine record (p-values, disposition, costs) |
| `results/xau_frozen_multi_year_costed_skeptic.md` | Pre-null: Donchian only remaining interesting lane after spread |
| `results/xau_null_maxstat.md` | bb_rsi family already **DEAD** (`KILL_BB_RSI_LINE`) |
| `results/xau_loop_status.md` | Loop context: next_step was this Donchian null |

---

## 1. Disposition and p-values (quoted)

From `xau_donchian_null_maxstat.md` / `.json`:

| Field | Value |
|-------|--------|
| **Disposition** | **`KILL_DONCHIAN_LINE`** |
| **p_max_pf** | **0.195** (`p(null ≥ real) = 0.1951219512195122`) |
| **p_n_passers** (soft primary) | **0.293** (`0.2926829268292683`) |
| **p_n_passers_classic** | **0.341** (`0.34146341463414637`) |
| **promote** | **no** |
| **live_go** | **false** |

**Reason (source text):**

> Real best-of-Donchian-grid is not distinguishable from return-shuffled nulls (p_max_pf=0.195, p_n_passers=0.293). The gates measured the search, not the market. Do not retune champions; do not promote. promote=no / live_go=false.

**Decision rule applied (source):**

- Fail (`KILL_DONCHIAN_LINE`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05`
- Pass (`PASS_KEEP_FROZEN`) only if both p-values ≤ 0.05 — still not live_go

Both primary p-values fail the 0.05 bar by a wide margin. Null max PF under the same search reaches **3.19** (null p90 ≈ 2.32) while real max PF (n≥20) is **1.996**. Real soft n_passers = **19**; null can put up to **308** soft passers on shuffled returns (null p90 ≈ 91). Real best-of-grid is typical of noise.

### Protocol snapshot (not re-argued)

- Window: develop only (`time < 2026-01-01`), 25582 H1 bars; holdout sealed  
- Grid: 1201 configs (max_n=1200, seed=42, frozen_prepended=2) — no early exit  
- Null: 40 return-shuffle trials, base_seed=20260808  
- Costs: measured spread (`spread_col=spread`, `point_size=0.01`); commission/slippage still 0  
- Soft gates primary: PF≥1.5, n≥40, DD≤12, expectancy≥20  
- Frozen catalog baselines on same window: neither soft-pass nor classic-pass (PF 1.49 / 1.52, DD 30% / 33%)

---

## 2. KILL path — RESEARCH_IDLE (strategy edge)

This is a **KILL**, not a pass. Per the costed multi-year skeptic §6 outcome table and this test’s own rule:

| Domain | Action |
|--------|--------|
| **Strategy-edge work** | **`RESEARCH_IDLE`** — stop searching Donchian / turtle grids, stop champion retunes, stop “one more ablate” on this family |
| **Virgin / process hygiene** | **`WAIT_DATA` only** — sealed post-peek virgin bars may still accumulate for *process* completeness (coverage, export hygiene). That is **not** permission to mine, retune, or promote from Donchian on virgin data |
| **promote** | **no** |
| **live_go** | **false** |
| **PAPER_GO** | **no** |

Multi-year calendar-year +NP under spread (`xau_frozen_multi_year_costed_skeptic.md`) was a **research survivor flag**, not market edge. The null max-stat test was the decisive filter: the develop-window search that “found” Donchian strength also finds equal-or-better max stats on return-shuffled paths. **Do not launder KILL into PASS_KEEP_FROZEN** by re-ranking frozen turtle cells or re-labeling IS years.

There is **no** remaining interesting strategy lane from the frozen catalog for further edge research:

| Lane | Status |
|------|--------|
| **bb_rsi / vol-gate family** | Already **`KILL_BB_RSI_LINE`** (p_max_pf=0.854, p_n_passers=0.707) |
| **Donchian / turtle** | **`KILL_DONCHIAN_LINE`** (this test) |
| ATR trail / refined ATR | Collapsed multi-year under costs (2023–24) |
| HTF pullback | Sign-flip 2023 under costs |
| HTF fib (baseline / refined) | Thin-n and/or peeked negative under costs |

---

## 3. PASS branch (not taken)

If both p-values had been ≤ 0.05, doctrine would still have been:

- **promote=no** / **live_go=false**
- Permission only to **keep frozen Donchian** for a future **sealed virgin** eval
- Not a paper or live ticket

**That branch did not fire.** No keep-for-virgin research mandate follows from this result. Catalog files may remain on disk as historical artifacts; they are not active candidates.

---

## 4. Explicit prohibitions

| # | Rule | Binding |
|---|------|---------|
| 1 | **Do not retune** Donchian / turtle champions, grids, or “small knob cuts” on develop or peeked windows | Yes |
| 2 | **Do not cross-instrument yet** (EURUSD, BTC, etc.) — null-failed families do not get a free transfer | Yes |
| 3 | **Do not revive bb_rsi** (or vol-gate as a research family) — prior null kill stands | Yes |
| 4 | **Do not** re-mine `year_2026_to_peek`, re-label 2024–2025 as OOS, or promote from multi-year +NP tables | Yes |
| 5 | **Do not** run `live_trader.py --live` or place orders from tests/smoke without explicit user consent (and there is no LIVE_GO from this work) | Yes |

---

## 5. Housekeeping still open (non-research)

These do **not** advance edge claims or promote. Track separately from the research loop:

| Item | Note |
|------|------|
| **Charter PR / doctrine sync** | `xau_lane_opt_charter.json` vs actual discard policy (`KILL_BB_RSI_LINE`, `KILL_DONCHIAN_LINE`, PARK pullback, costs defaults); platform charter vs research layer boundaries |
| **CSV history hygiene** | Spread-bearing export discipline; fit-window / sha256 on `strategy_params.json`; do not extend CSV under frozen metrics without `slice_to_window` |
| **Exness symbols / multi-broker paths** | Brand install dirs, `MT5_BRIDGE_DIR`, broker env scripts — ops/platform, not XAU edge |
| **Ruff / lint** | `uv run ruff check src tests` — code quality only |

Optional process-only: when enough **unpeeked** virgin bars exist, a single pre-registered frozen-catalog replay (no search) remains allowed as hygiene — **not** as a path to promote from killed families.

---

## 6. Explicit promote ruling

### promote = **no** · live_go = **false** · PAPER_GO = **no**

| Gate | Status |
|------|--------|
| **promote** | **no** |
| **PAPER_GO** | **no** |
| **LIVE_GO** | **false** |
| Strategy disposition | **`KILL_DONCHIAN_LINE`** → **`RESEARCH_IDLE`** |
| Process / virgin | **`WAIT_DATA`** only (hygiene, not edge) |
| bb_rsi | **DEAD** — do not revive |
| Donchian | **DEAD** as searchable edge — do not retune |

Safety: offline only. Fail closed. The impossible bar for promote (sealed virgin hard_pass of a null-surviving family) is not in play; both major families are null-killed.

---

## 7. Checklist vs assigned requirements

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Quote disposition and p-values | **§1** — `KILL_DONCHIAN_LINE`; p_max_pf=0.195; p_n_passers=0.293 |
| 2 | If KILL: RESEARCH_IDLE for strategy-edge; virgin WAIT_DATA only for process hygiene | **§2** |
| 3 | If PASS: still promote=no / keep frozen for sealed virgin — **N/A (KILL)** | **§3** |
| 4 | Explicit: no retune, no cross-instrument yet, no revive bb_rsi | **§4** |
| 5 | Housekeeping still open (charter PR, CSV history, Exness symbols, ruff) | **§5** |

---

## 8. Disposition

| Field | Value |
|-------|--------|
| **ok (artifact written)** | true |
| **promote** | **no** |
| **live_go** | **false** |
| **Donchian** | **`KILL_DONCHIAN_LINE`** |
| **bb_rsi** | **`KILL_BB_RSI_LINE`** (prior; unchanged) |
| **strategy next_step** | **`RESEARCH_IDLE`** |
| **process next_step** | virgin **`WAIT_DATA`** (hygiene only) |
| **summary** | KILL_DONCHIAN_LINE (p_max_pf=0.195, p_n_passers=0.293) → RESEARCH_IDLE; promote=no / live_go=false |

*Hostile one-liner: Multi-year green Donchian under spread was search theater — null max-stat puts p≈0.20–0.29 on the same develop grid; both edge families are dead; sit idle on strategy work and only wait on sealed data for process completeness.*
