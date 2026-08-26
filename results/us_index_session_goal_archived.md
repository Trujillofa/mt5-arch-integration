# US-index 1% / 20% goal — archived (falsified)

**Date:** 2026-08-20  
**Status:** **ARCHIVED** · `promote=no` · `live_go=false`  
**Lane:** US100 / US30 session-scalp research (`us_index_session_*` v1–v8)

## Stage 1 — close the gap gate

The retail index CFD goal — median **trade-day ≥ 1%** and median **trade-month ≥ 20%** on the frozen **$10k / 1 lot / 10 MT5-point slip** book — is **falsified** under that book’s ~20-point round-trip (slip + typical cash spread). Every develop/holdout screen missed both bars. Cost/size once: 0/5 books hit both goals; more lots scale the same (near-zero) edge.

Do **not** retune v1–v8, raise lots, or cut slip to manufacture 1%/20%. Do **not** reopen news-drift, M1, US500, or Timescale-as-`tick_volume`.

| Field | Value |
|-------|--------|
| **Role now** | Observe-only live overlay + archived offline screens |
| **Overlay** | `UsIndexSessionScalp` v1.40 · signal buffer 8 · no `OrderSend` |
| **Logger** | `ForexSignalLogger` log-only (`MaxSpreadPips=0`) if attached |
| **Pass gate** | **Dropped** (1%/20% no longer a research target on this book) |
| **Active strategy research** | **Moved to XAUUSD** — see `results/xau_loop_status.md` |

FP `CopyTicks` 36h on US100 was quote-only (`last==0`). That does not reopen an index tape family.

## Overlay (keep)

Session mapping (NY OR, VWAP, EMA clouds) and optional signal logging stay useful as **context**. They are not an execution model.

Operator path: [docs/MT5-INTEGRATION-CAPABILITIES.md](../docs/MT5-INTEGRATION-CAPABILITIES.md). Offline replay: [docs/HOWTO-US-INDEX-SCALP.md](../docs/HOWTO-US-INDEX-SCALP.md).
