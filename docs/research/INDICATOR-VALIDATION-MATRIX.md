# Indicator validation matrix

**One row per overlay, one row for the python-only index v8 screen. Last column starts blank — no cell may say "validated" without a SHA-bound cross-engine envelope (see `trading-evidence`, adapter `mt5.lane_verdict` — not yet defined).**

Replay evidence below was produced 2026-09-11 (P4b regression pass): every committed disposition reproduced **byte-identically** from its lock. Drift anywhere ⇒ stop and investigate before any new search.

| Indicator / screen | Signal buf | Lives on | Offline lane (lock sha256-12) | Develop PF | Holdout PF | Null | Disposition | Cross-validated |
|---|---:|---|---|---:|---:|---|---|---|
| `UsIndexSessionScalp` v1.41 (US30 M5 flatten replay) | 8 | main | M5 replay, no grid (`prior_us30.json`, btc-wt) | 1.20 (+$2,539) | **0.50** (−$4,383) | n/a | observe-only, promote=no | |
| `UsIndexSessionScalp` v1.41 (US100 M5 flatten replay) | 8 | main | M5 replay, no grid (`prior_us100.json`, btc-wt) | 0.72 | 0.95 | n/a | observe-only, promote=no | |
| US-index **v8** H1 squeeze + H4 fib (python-only) | n/a | index-wt | `us_index_session_v8_lock.json` `aa703337561e` | 0/32 eligible | — (eval-only) | — | **SCREEN_FAIL** | |
| `GoldSessionScalp` (M5) | 8 | **xau-wt only** | `xau_session_scalp/lock.json` `d1d809e0c239` + `defined_r_v1_lock.json` `252675524d71` (holdout 2026-01-01 ← `xau_holdout_lock.json` `99291c8396cd`) | 0.80–0.83 (n≈230–319) | 0.88 | — | **CLOSED** 2026-09-09; hard forbids in `STATUS.md` | |
| `BtcNySessionScalp` v1.00 (M5 NY-desk overlap) | 8 | **btc-wt only** (PR #98) | `btc_ny_session_scalp_lock.json` `16c6fed87fec` (holdout 2026-03-01) | 0.70–0.75, 0/96 eligible | — (eval-only) | `frac_null_ge_real = 1.00` (10 seeds) | **SCREEN_FAIL** 2026-09-11; overlay = a-priori family | |
| `BtcTrendPullback` (H1/H4) | 7 | main | **NONE — no lock, no PF, never searched in this repo** | — | — | — | observe-only by convention; **P4a gap** | |
| `ForexHtfPivotsFib` v1.45 | 8 | main | `htf_fib_offline_lock.json` `45e491363779` (single-config, frictionless replay — not a money screen) | n/a (replay) | n/a | n/a | research-only | |
| `ForexIndicatorTemplate` | 9 | main | none | — | — | — | legacy/optional — **deprecated** (README optional; buffer table fixed in PR #99) | |

Other locked lanes (context, not overlays): EURUSD NY scalp `7d5d327beda6` (192 configs, 0 eligible → SCREEN_FAIL), EURUSD USD-book replay lock (expected fail), XAU H1 host `backtest.py` (charter-gated; standing disposition `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`, `xau_loop_status.md` — do not edit).

## P4b replay evidence (2026-09-11)

All from locks / committed data; outputs compared byte-for-byte, none of the official locks or terminal records rewritten:

| Replay | Command (read-only) | Result |
|---|---|---|
| XAU H1 host | `python3 backtest.py` (no `--save`) | runs clean; develop window sealed < 2026-01-01; nothing saved |
| BTC-NY v1 | `python3 scripts/btc_ny_session_scalp_autoresearch.py --out <tmp>` (btc-wt @ `d27a20a`+lint) | **96/96 `rows_slim` + transfers identical**; SCREEN_FAIL reproduced |
| Index v8 | `python3 scripts/us_index_session_autoresearch_v8.py --out <tmp>` (CSV sha256 still matches lock) | **entire JSON identical**; 0/32 eligible reproduced |
| US30/US100 M5 flatten | `python3 scripts/us_index_session_backtest.py --hc <FP M5.hc> …` | both **entire JSON identical** to `prior_us30/100.json` |
| Gold scalp | `python3 scripts/xau_session_scalp_backtest.py --mode all --out-dir <tmp>` (xau-wt) | `baseline/adjusted/candidates.json` **byte-identical**; lane stays CLOSED |

## Rules this matrix enforces

- Holdouts already taken (a new lane's `holdout.start` must be asserted outside this set): `2026-01-01` (XAU), `2026-03-01` (BTC-NY), `2026-06-01` (index v1; June also v8's burned buffer), `2026-07-01` (index v8), `2025-03-01` (EURUSD).
- A previously evaluated holdout never becomes develop for a sequel search.
- Re-running any screen against a **longer** live cache is a new search, not a replay — v8 replay above was valid only because its CSV sha256 still matched the lock.
- Every new lane needs: lock committed before first metric, lane-local holdout, 10-seed null, slim JSON+md, and a row here.
