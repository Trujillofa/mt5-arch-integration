# XAU offline loop status

## 2026-08-11 — MULTI-INSTRUMENT Phase 0 integrity v2 · PASS_DATA_READY_WITH_IMPUTATION

| Field | Value |
|-------|--------|
| **next_step** | **`AWAIT_ADVERSARIAL_DATA_RE_REVIEW`** (integrity v2) → then multi-instrument family freeze |
| **gate** | **`PASS_DATA_READY_WITH_IMPUTATION`** |
| **export_run_id** | `158e5a16fc9a491d96d7f499f7fa1f86` |
| **MQL complete** | terminal_connected=true · login=27496181 · server=VantageMarkets-Live 5 |
| **EURUSD rows** | **30694** (restored; unit tests isolated from OUT_DIR) |
| **artifact lock** | `results/instrument_data_manifests/committed_artifact_lock.json` verified |
| **clock** | server_clock_as_stored |
| **joint intersection** | 25557 develop H1 (XAU=intersection; EUR≡GBP; XAU⊂FX) |
| **thesis freeze / scoring** | **not authorized** |
| **promote / live_go / PAPER_GO** | **no / false / no** |

Integrity v2: isolated test writes, no publish on hard fail, export_run SHA/size/mtime + export_complete runtime account, symbol/H1 alignment checks.

---

Closed on main: day_open_reclaim_flat v2 SCREEN_FAIL.
