# Thesis memo — `exog_london_fx_cosign_xau_follow_flat` v1

**Date:** 2026-08-15  
**Status:** **FREEZE_ONLY** — charter + memo · **no develop package load · no screen · no null · no fixtures run**  
**Branch:** `research/exogenous-predictor-phase-c-freeze` from `main@47ae0e7` (PR #11 Phase B merged)  
**Charter:** `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v1.json`  
**Protocol:** `docs/research/MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md` · harness `multi_instrument_exogenous_predictor_v1`

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); selection never uses holdout  
- Closed freezes stay closed — especially **do not retune** `joint_london_open_cosign_fade_flat`  
- Catalog open: PASS is provisional; paper/live forbidden while open  
- This freeze does **not** peek develop PF/NP/DD or authorize scoring

## Market mechanism

On the multi-instrument Phase-0 package (XAUUSD, EURUSD, GBPUSD H1, `server_clock_as_stored`), restrict analysis to the **intersection calendar I**.

**Predictors only (no orders):** EURUSD and GBPUSD.  
**Traded book (exactly one):** XAUUSD.

Per server calendar day \(D\), let \(T^\*\) be the earliest bar on **I** with date \(D\) and server hour in \(\{7,8,9\}\). If none → no candidate that day.

At \(T^\*\), compute predictor open→close returns:

- \(r_{\text{EUR}} = \text{close}_{\text{EUR}} - \text{open}_{\text{EUR}}\)  
- \(r_{\text{GBP}} = \text{close}_{\text{GBP}} - \text{open}_{\text{GBP}}\)

**FX cosign (predictors):** both returns nonzero and equal sign \(s \in \{+1,-1\}\).

**XAU follow (traded):** if FX cosign holds, admit a candidate with side \(= s\) (same direction as FX). Gold is hypothesized to **follow** the early FX impulse (USD-proxy weakness → risk appetite / gold bid when EUR+GBP print the same positive sign; the reverse for negative). **XAU’s own \(T^\*\) bar is not used in the signal predicate** — only predictors form the event.

Entry / hold follow exogenous protocol v1 (canonical, not free knobs):

- Entry at open of next joint bar \(T^\*+1\) (never at \(T^\*\) open/close)  
- Fixed H=3 hold bars including entry; same `day_id` for \(T^\*\), entry, and all hold bars or reject  
- Fixed-H occupancy: overlapping reserved intervals forbidden  
- Wilder ATR14 on **traded** series on I at \(T^\*\); SL 1.5×ATR, TP 2.0×ATR  
- Lot sizing from \(B_{\text{in}}(t_{\text{entry}})\) only (carry-in balance)  
- Exit: SL then TP then time-flat at close of entry+H−1  
- Costs: house RT at entry spread (donor/real entry bar)

Null: `conditional_fixed_signal_events_fixed_trades_v1` (N≥999), not OHLC-rotate joint shared-k.

## Sign mapping (toy examples)

| EUR \(r\) | GBP \(r\) | Cosign? | Traded XAU side |
|-----------|-----------|---------|-----------------|
| +0.0012 | +0.0008 | yes \(s=+1\) | **long** XAU |
| −0.0009 | −0.0011 | yes \(s=-1\) | **short** XAU |
| +0.0010 | −0.0005 | no | no event |
| +0.0000 | +0.0010 | no (zero leg) | no event |

## Expected sign (gates — not develop metrics)

After Standard STP costs (measured spread; commission 0; slip 0 unmeasured):

- Soft primary (binary on **traded** book only): n≥20, PF≥1.1, NP>0, DD≤25%  
- Soft passers ∈ {0,1}. Zero → **SCREEN_FAIL**, null not armed, r1 unburned  
- One passer → sealed null under exogenous accounting; provisional PASS only if p ≤ α_adj = 0.05/9  

Under null: if the FX→gold link is only calendar coincidence / segment chance, fixed-event fixed-trade transplants should match or beat real soft pass → **KILL**.

## Explicit failure modes

1. FX cosign is noise for gold; followers lose after spread.  
2. H=3 truncates trends; SL/TP geometry wrong for XAU.  
3. Edge is residual of joint-cosign fade already SCREEN_FAIL — this family **does not** require XAU cosign and **does not** fade (it follows FX only).  
4. Soft passers = 0 → SCREEN_FAIL without null.  
5. Soft passer = 1 but null p > α_adj → KILL_EXOG_LONDON_FX_COSIGN_XAU_FOLLOW_FLAT.  
6. Occupancy / same-day attrition empties E → SCREEN_FAIL or invalid run (fail closed).

## Why this is not a closed family

| Closed / parked line | Difference |
|----------------------|------------|
| `joint_london_open_cosign_fade_flat` | Required **all three** symbols cosign and **faded all three** books under `multi_instrument_joint_v1`. This uses **EUR+GBP predictors only**, trades **XAU only**, **follows** FX sign, harness `multi_instrument_exogenous_predictor_v1`, null is conditional fixed-event/fixed-trade — not shared-k OHLC rotate. |
| `tod_london_ny_flat` / `server_hour_window_flat` | Single-frame fixed-hour long; no FX predictors. |
| `early_server_range_break_flat` / `day_open_reclaim_flat` | Single-frame XAU geometry; no multi-instrument predictors. |
| `bb_rsi` / Donchian / `prior_day_high_break` | Single-frame indicator families; dead/killed. |

Not a rename, filter, or retune of joint cosign.

## Free knobs

**Zero.** Search cardinality = 1.

Fixed: coincident hours {7,8,9}, FX cosign predicate, follow mapping, H=3, SL/TP ATR 1.5/2.0, Wilder 14, risk 1%, lot_min/step/max 0.01/0.01/0.5, start_balance 10k on traded book.

## Null

- `null.method` = `null.implementation_id` = `conditional_fixed_signal_events_fixed_trades_v1`  
- N = 999 · base_seed = 20260815  
- Multiplicity: K_prior=8 · K=9 · α_adj=0.05/9 · provisional · paper_live_while_open=false  

## Kill label

`KILL_EXOG_LONDON_FX_COSIGN_XAU_FOLLOW_FLAT`

## Phase gate

| Step | Status |
|------|--------|
| Phase A protocol | merged (#10) |
| Phase B engine/validator | merged (#11 @ 47ae0e7) |
| Phase C charter + memo | **this PR — AWAIT freeze review** |
| Fixtures / family module / screen | **not authorized** until freeze AUTHORIZE |
| Null / paper / live | **forbidden** until later AUTHORIZE |

**End of Phase C freeze memo (v1).**
