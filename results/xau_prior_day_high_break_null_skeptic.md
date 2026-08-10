# XAU prior_day_high_break Null / Max-Stat — Hostile Skeptic

**Date:** 2026-08-08  
**Stance:** Fail closed. Safety: `promote=no` / `live_go=false`. No retune after KILL.  
**Pipeline phase:** Decisive offline null test of the charter-frozen next family (`prior_day_high_break`). No walk-forward after KILL. No `--live`.

**Artifacts reviewed:**

| Path | Role |
|------|------|
| `results/xau_prior_day_high_break_null_maxstat.md` | Protocol, real grid, null table, disposition |
| `results/xau_prior_day_high_break_null_maxstat.json` | Machine record (p-values, disposition, costs) |
| `results/xau_prior_day_high_break_develop_grid.json` | Pre-null develop full-grid score (3 configs, RAW costs) |
| `results/xau_next_design_charter.json` / `.md` | Frozen family + kill rules |
| `results/xau_donchian_null_maxstat.md` | Prior: `KILL_DONCHIAN_LINE` |
| `results/xau_null_maxstat.md` | Prior: `KILL_BB_RSI_LINE` |
| `results/xau_loop_status.md` | Loop context |

---

## 1. Disposition and p-values (quoted)

From `xau_prior_day_high_break_null_maxstat.md` / `.json`:

| Field | Value |
|-------|--------|
| **Disposition** | **`KILL_PRIOR_DAY_HIGH_BREAK`** |
| **p_max_pf** | **0.463** (`0.4634146341463415`) |
| **p_n_passers** (soft primary) | **1.000** |
| **p_n_passers_classic** | **1.000** |
| **promote** | **no** |
| **live_go** | **false** |

**Reason (source text):**

> Real best-of-prior_day_high_break-grid is not distinguishable from return-shuffled nulls (p_max_pf=0.463, p_n_passers=1.000). The gates measured the search, not the market. Do not tune further; do not promote.

**Decision rule applied (charter + harness):**

- Fail (`KILL_PRIOR_DAY_HIGH_BREAK`) if `p_max_pf > 0.05` **or** `p_n_passers > 0.05`
- Pass only if both ≤ 0.05 (and real n_passers > null p90) — still not live_go; walk-forward would be next only on PASS

Both primary p-values fail the 0.05 bar. Real max PF (n≥20) = **1.077**; null max under the same 3-config search reaches **1.308** (null p50 ≈ 1.05, p90 ≈ 1.24). Real soft n_passers = **0** (charter soft: n≥20, PF≥1.2, NP>0); null can put up to **2** soft passers on shuffled returns. Real best-of-grid is typical of noise — and does not even clear the soft gate once.

### Protocol snapshot

- Window: develop only (`time < 2026-01-01`), 25582 H1 bars; holdout sealed  
- Grid: **3** configs (`sl_atr` ∈ {1.0, 1.5, 2.0}); full enumerate; no early exit  
- Null: 40 return-shuffle trials, base_seed=20260808, workers=8  
- Costs: RAW floor — `spread_col=spread`, `point_size=0.01`, `commission_per_lot=3.0`, `slippage_points=0.0`  
- Soft primary (charter): n≥20, PF≥1.2, net_profit > 0  
- Classic diagnostic: n≥20, PF>1.5, WR>55, DD<10  

*(Note: harness markdown labels soft gates with a generic turtle string; the family plugin’s `soft_pass` implements the charter definition above — real/null soft counts match PF≥1.2.)*

---

## 2. After KILL — no refine, no WF, RESEARCH_IDLE

Charter §7: after KILL, **stop**. Explicitly forbidden:

- widen `sl_atr` grid  
- free `tp_rr`, hours, ATR period, cooldown, or trend filters  
- add RSI/BB/Donchian overlays  
- re-run with frictionless costs  
- “one more try” under the same `family_id`  
- walk-forward on a killed family (WF is only for null survivors)  

**KILL is a valid success of the scientific process.** Do not retune to rescue PF 1.08.

| Field | Value |
|-------|--------|
| **strategy next_step** | **`RESEARCH_IDLE`** |
| **process** | New family only via **new charter freeze** (new `family_id`) |
| **holdout** | Remains sealed; no peek justified by this family |

---

## 3. PASS path — N/A (this fire is KILL)

If null had passed: next step would be **costed walk-forward only** (still promote=no). That path is closed.

---

## 4. Dead lines — do not revive

| Line | Status |
|------|--------|
| bb_rsi / rsi_cross | `KILL_BB_RSI_LINE` |
| Donchian / turtle | `KILL_DONCHIAN_LINE` |
| prior_day_high_break | **`KILL_PRIOR_DAY_HIGH_BREAK`** (this fire) |

---

## 5. Hostility checklist

| # | Requirement | Result |
|---|-------------|--------|
| 1 | Quote disposition and p-values | **§1** — KILL; p_max_pf=0.463; p_n_passers=1.000 |
| 2 | If KILL: RESEARCH_IDLE; no retune | **§2** |
| 3 | If PASS: walk-forward only / promote=no — **N/A (KILL)** | **§3** |
| 4 | No bb_rsi/Donchian revival; no same-id refine | **§4** |
| 5 | Costs charged (RAW $3 + spread) | yes — not frictionless |
| 6 | Full grid (n=3), n_null=40 | yes |

---

## 6. Disposition

| Field | Value |
|-------|--------|
| **ok (null artifacts + disposition written)** | **true** |
| **promote** | **no** |
| **live_go** | **false** |
| **family** | **`KILL_PRIOR_DAY_HIGH_BREAK`** |
| **strategy next_step** | **`RESEARCH_IDLE`** |
| **summary** | KILL_PRIOR_DAY_HIGH_BREAK (p_max_pf=0.463, p_n_passers=1.000) → RESEARCH_IDLE; promote=no / live_go=false; do not retune |

*Hostile one-liner: Charter family’s best develop PF is 1.08 with zero soft passers under RAW costs; return-shuffle nulls match or beat it (p_max_pf≈0.46, p_n_passers=1.0) — KILL, sit idle, new charter only for any next family.*
