# Simulator conformance (hand-derived)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-21 |
| **Branch** | `research/simulator-conformance` |
| **Suite** | `tests/test_simulator_conformance.py` + `tests/fixtures/simulator_conformance/` |
| **Standing** | `promote=false`, `live_go=false` — **authorizes no revival** |

Offline engines produced every closed-family verdict in this repo. This suite is the first evidence those engines match **their declared contracts** on hand-checkable arithmetic. It is instrument validation, not research.

## Hard rule

Expected values are **derived on paper** (each fixture ships a `derivation` string). Engines were **not** edited to force PASS. A test that only echo-matches engine output is forbidden.

## Engines × clauses

| Engine | C1 entry | C2 SL-first | C3 no same-bar exit | C4 gap | C5 bid-space short | C6 RT cost | C7 lot floor | C8 force-flat | C9 pivot | C10 equity floor |
|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `backtest.simulate` (XAU) | N/A* | N/A* | **PASS** | N/A | N/A | **PASS** | N/A | N/A | N/A | N/A |
| `eurusd_ny_scalp_autoresearch` | **PASS** | **PASS** | N/A†† | **PASS** | **PASS** | **PASS** | **PASS** | N/A† | N/A | N/A† |
| `us_index_session_backtest` | N/A‡ | N/A‡ | N/A | N/A | N/A | **PASS** | N/A | N/A | N/A | N/A |
| `htf_fib_offline` (`simulate_from_signals`) | N/A‡ | N/A‡ | **PASS** | N/A | N/A | N/A (frictionless) | N/A | N/A | N/A | N/A |
| `htf_fib_core` | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | **PASS** | N/A |

\*XAU full-path C1/C2 still N/A here (indicator warmup); C3 asserted via trunc-series discriminator (eod NP≈0 vs same-bar SL ~−90).  
†EURUSD C8/C10 already locked in `tests/test_eurusd_ny_scalp.py`; not duplicated.  
††EURUSD is next-bar-open entry — same-bar exit is a different clause; not the XAU/HTF close-fill lookahead signature.  
‡Full US path sims need market CSVs — cost pure clause tested.

**Divergences:** **0**

**Mutant gate:** `test_c2_mutant_tp_first_is_caught` rewrites the **real engine source**
(`scripts/eurusd_ny_scalp_autoresearch.py`), reordering the exit loop to check TP before SL,
loads the result as a separate module, and asserts the C2 fixture flips `sl` → `tp`. The
mutation is anchored on three exact source lines; if a refactor moves any of them the gate
**fails loudly** ("repair this gate before trusting the suite") rather than degrading into a
tautology. Verified end-to-end: a genuinely TP-first engine fails both C2 tests.

lookahead signature and therefore the highest-value clause still untested; closing it needs
indicator warmup fixtures or the Strategy Tester path, not a thin unit suite.

**Regression gate:** `test_eurusd_ny_scalp` + `test_xau_pipeline` + `test_htf_fib_pivot_confirmation` → **43 passed, 1 skipped** (engines unchanged).

## Sample hand arithmetic (spot-check)

| Clause | Result | Derivation (abridged) |
|--------|--------|------------------------|
| C6 XAU | PASS $3.00 | (20+10)×0.01×100×0.10 = 3.00 |
| C6 EUR | PASS $3.96 | (12+10)×1e-5×100000×0.18 = 3.96 |
| C6 US | PASS $0.80 | (60+20)×0.01×1×1 = 0.80 |
| C7 lots | PASS 0.18 | floor(100/540)=floor(0.185…)=0.18; risk $97.20 ≤ $100 |
| C5 short | PASS | levels − 12×1e-5; raw-vs-exit phantom = 12 pts |
| C9 pivot | PASS | center=3, active=3+2=5; not active at center |
| C2 SL-first | PASS | both-touch → exit at SL 1.09450, not TP |

## What this means for closed verdicts

With **zero DIVERGENCE** on the declared contracts tested here, the 24-family dead ledger in `docs/research/BACKTEST-RECORD.md` still rests on engines that **match their stated fill/cost/causality arithmetic** on these clauses.

That is a **success**, not a null result: it is the first conformance evidence in-repo.

## If a DIVERGENCE appears later

It does **not** revive a family. It sizes an error and names which verdicts would need re-running under a **new** `search_id` with fresh freeze-before-peek. Acting on that is **not** authorized by this document.

## This authorizes no revival

- No reopen of closed `family_id` / `search_id`
- No screen, null, grid, holdout read, lock/charter/`xau_loop_status` edit
- `promote=false`, `live_go=false`
