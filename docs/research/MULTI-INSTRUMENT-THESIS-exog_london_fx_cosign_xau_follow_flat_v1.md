# Thesis memo — `exog_london_fx_cosign_xau_follow_flat` v1

**Date:** 2026-08-15 (v4 re-freeze amendment — metric basis)  
**Status:** **FREEZE_ONLY** — charter + memo · **no develop package load · no screen · no null**  
**Charter:** `results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json` · SHA `3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5`  
**Supersedes chain (none scored):**  
- v3 `…_v3.json` · SHA `10ab933be675af39d3459b75d40792893027188794fa6ded668e73ac4c1cc4eb` (stratum definition + resolution + enforcement locus; immutable)  
- v2 `…_v2.json` · SHA `a5661ec34e457cbb05d999f92251d443fd86c04cf6d9980dcfc31a8c74762174` (provenance + stratified gate + ATR pin; immutable)  
- v1 `…_v1.json` · SHA `db7b015aea51ff743ec9d6318de2a1c782824bc6333995591e65a83526b0cb9d` (design only; immutable)  
**Protocol:** `docs/research/MULTI-INSTRUMENT-EXOGENOUS-PREDICTOR-PROTOCOL-V1.md` · harness `multi_instrument_exogenous_predictor_v1`

## Standing constraints

- promote=no · live_go=false · PAPER_GO=no · offline only  
- Holdout sealed (`holdout_start=2026-01-01`); selection never uses holdout  
- Closed freezes stay closed — especially **do not retune** `joint_london_open_cosign_fade_flat`  
- Catalog open: PASS is provisional; paper/live forbidden while open  
- This freeze does **not** peek develop PF/NP/DD or authorize scoring  
- Do **not** report a pooled-only soft passer

## Provenance

The **follow** direction was chosen **after** observing `joint_london_open_cosign_fade_flat` v4 **SCREEN_FAIL** on the same develop package, the same intersection calendar I, the same hours {7,8,9}, the same H=3, and the same ATR 1.5/2.0. That closed family **faded** when all three symbols cosigned; this family **follows** FX on a predicate that is a **strict relaxation** (XAU cosign requirement dropped). The event sets therefore **overlap**: on every day where XAU also cosigned at \(T^\*\), this family takes the **exact sign-inverse** of trades already scored under the closed family. Multiplicity \(K=9\) corrects for nine separate looks; it does **not** correct for re-testing one look with knowledge of its outcome. The stratified soft gate (below) is what requires fresh evidence on the non-overlap stratum. Observed artifact: `results/xau_runs/2026-08-14_joint_london_open_cosign_fade_flat_screen_r1/`.

## Market mechanism

On the multi-instrument Phase-0 package (XAUUSD, EURUSD, GBPUSD H1, `server_clock_as_stored`), restrict analysis to the **intersection calendar I**.

**Predictors only (no orders):** EURUSD and GBPUSD.  
**Traded book (exactly one):** XAUUSD.

Per server calendar day \(D\), let \(T^\*\) be the earliest bar on **I** with date \(D\) and server hour in \(\{7,8,9\}\). If none → no candidate that day.

At \(T^\*\), compute predictor open→close returns:

- \(r_{\text{EUR}} = \text{close}_{\text{EUR}} - \text{open}_{\text{EUR}}\)  
- \(r_{\text{GBP}} = \text{close}_{\text{GBP}} - \text{open}_{\text{GBP}}\)

**FX cosign (predictors):** both returns nonzero and equal sign \(s \in \{+1,-1\}\).

**XAU follow (traded):** if FX cosign holds, admit a candidate with side \(= s\) (same direction as FX). Gold is hypothesized to **follow** the early FX impulse (USD-proxy weakness → risk appetite / gold bid when EUR+GBP print the same positive sign; the reverse for negative). **XAU’s own \(T^\*\) bar is not used in the signal predicate** — only predictors form the event. (Whether XAU’s open→close at \(T^\*\) matches \(s\) is a **reporting stratum only** — it does not enter the entry predicate.)

Entry / hold follow exogenous protocol v1 (canonical, not free knobs):

- Entry at open of next joint bar \(T^\*+1\) (never at \(T^\*\) open/close)  
- Fixed H=3 hold bars including entry; same `day_id` for \(T^\*\), entry, and all hold bars or reject  
- Fixed-H occupancy: overlapping reserved intervals forbidden  
- Wilder ATR14 on **traded** series on I at \(T^\*\) — charter pins `atr_reference_bar=T_star` (ATR must not be taken at the entry bar; that would be lookahead)  
- SL 1.5×ATR, TP 2.0×ATR  
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

- Soft primary field `gates.primary_n_passers` remains the literal **`"soft"`** (protocol-locked by Phase B). Soft thresholds on **traded** book only: n≥20, PF≥1.1, NP>0, DD≤25%.  
- Soft passers ∈ {0,1} under the resolution order below. Zero → **SCREEN_FAIL**, null not armed, r1 unburned.  
- One passer (pooled **and** fresh stratum) → sealed null under exogenous accounting; provisional PASS only if p ≤ α_adj = 0.05/9.

### Stratified requirement — definition, order, enforcement

**Not machine-enforced by Phase B.** `gates.stratified_required` is ignored by the merged validators/resolvers; they only read `primary_n_passers == "soft"`. The enforcement locus is therefore the family module `scripts/xau_family_exog_london_fx_cosign_xau_follow_flat.py` (not yet authorized). That module **must** evaluate both strata and **must fail closed** (raise / refuse) if stratified evaluation is absent, empty, or unreportable. Reporting a pooled-only soft passer is a protocol violation. The screen artifact must emit n, PF, NP, DD **per stratum plus pooled**.

**Stratum definition (ternary variable → binary strata):**

- Variable: \(\mathrm{sign}(\mathrm{close}_{XAU}(T^*) - \mathrm{open}_{XAU}(T^*))\) on the traded series, on calendar I, at \(T^*\) only.  
- \(s\) = FX predictor cosign of the same event.  
- `xau_cosign_at_tstar`: XAU \(T^*\) open→close is **nonzero** and its sign equals \(s\).  
- `xau_not_cosign_at_tstar`: **everything else** — including an **exactly-zero** XAU \(T^*\) open→close, and including sign equal to \(-s\).  
- The variable is ternary (\(+s\), \(-s\), \(0\)); the strata are binary. Zero-return assignment to `xau_not_cosign_at_tstar` is **fixed here**, not an implementation choice.  
- Reporting label **only** — must never enter entry predicate, sizing, SL/TP, or exit.

**Resolution order:**

1. Soft pass requires **both** the pooled soft gate **and** the `xau_not_cosign_at_tstar` stratum soft gate.  
2. If the fresh stratum fails → **SCREEN_FAIL**; null is **not** armed; r1 stays **unburned**; no sealed cycle.  
3. If both pass → one soft passer; proceed to sealed null; provisional PASS only if p ≤ 0.05/9.  
4. Pooled-only pass is **not** sufficient and must not be reported as a passer.

### Metric basis (v4)

Declared during Phase D implementation, **before any develop screen**; the stratum split is unknown at declaration time.

- **Stratum DD:** `max_drawdown_pct` on a stratum is the drawdown of that stratum’s own **ordered pnl subsequence**, with equity reconstructed from that subsequence alone starting at `fixed.start_balance`. Trades in the other stratum are **omitted**, not held flat.  
- **Pooled DD:** full mark-to-market equity path from the exogenous harness real path.  
- **Asymmetry:** pooled DD and per-stratum DD use **different accounting bases** but are compared to the **same** `gates.soft.max_drawdown_pct_max`. Unavoidable (a stratum has no pooled MTM path of its own); declared rather than “fixed” by changing thresholds.  
- **Expected bindingness:** the stratum equity path is strictly shorter than pooled, so DD is expected to bind **less** on the fresh stratum than on pooled. The effectively binding fresh-stratum soft components are `n_trades_min`, `profit_factor_min`, and `net_profit_gt`.  
- **`n_trades_min` on the stratum:** `gates.soft.n_trades_min` applies to `xau_not_cosign_at_tstar` on its **own** trade count. Fewer than `n_trades_min` fresh trades → stratum fail → **SCREEN_FAIL** (null unarmed, r1 unburned). Not a waiver, not a pooled fallback, and not grounds to lower `n_trades_min`.

Under null: if the FX→gold link is only calendar coincidence / segment chance, fixed-event fixed-trade transplants should match or beat real soft pass → **KILL**.

## Explicit failure modes

1. FX cosign is noise for gold; followers lose after spread.  
2. H=3 truncates trends; SL/TP geometry wrong for XAU.  
3. Non-identity with the closed fade family is **not** independence. The predicates differ (no XAU cosign required; follow vs fade), but the event sets overlap, and on the overlap this family is the exact sign-inverse of an already-scored develop result. Bonferroni \(K\) does not fix that; the stratified gate is what makes the test carry fresh evidence.  
4. Soft passers = 0 → SCREEN_FAIL without null.  
5. Soft passer = 1 but null p > α_adj → KILL_EXOG_LONDON_FX_COSIGN_XAU_FOLLOW_FLAT.  
6. Occupancy / same-day attrition empties E → SCREEN_FAIL or invalid run (fail closed).

## Why this is not a closed family

| Closed / parked line | Difference |
|----------------------|------------|
| `joint_london_open_cosign_fade_flat` | Required **all three** symbols cosign and **faded all three** books under `multi_instrument_joint_v1`. This uses **EUR+GBP predictors only**, trades **XAU only**, **follows** FX sign, harness `multi_instrument_exogenous_predictor_v1`, null is conditional fixed-event/fixed-trade — not shared-k OHLC rotate. Overlap is declared in Provenance and gated by stratification. |
| `tod_london_ny_flat` / `server_hour_window_flat` | Single-frame fixed-hour long; no FX predictors. |
| `early_server_range_break_flat` / `day_open_reclaim_flat` | Single-frame XAU geometry; no multi-instrument predictors. |
| `bb_rsi` / Donchian / `prior_day_high_break` | Single-frame indicator families; dead/killed. |

Not a rename, filter, or retune of joint cosign — but also not an independent look at the overlapping stratum.

## Free knobs

**Zero.** Search cardinality = 1.

Fixed: coincident hours {7,8,9}, FX cosign predicate, follow mapping, H=3, SL/TP ATR 1.5/2.0, Wilder 14 at \(T^\*\), risk 1%, lot_min/step/max 0.01/0.01/0.5, start_balance 10k on traded book.

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
| Phase C charter + memo | **v4 metric-basis amendment — AWAIT merge then Phase D repoint** |
| Fixtures / family module | implemented locally against **v3**; must repoint to **v4** before Phase D PR |
| Develop screen / null / paper / live | **forbidden** until later AUTHORIZE |

**End of Phase C freeze memo (v1 filename; charter binding is v4).**
