# OnTradeTransaction journal

**Status:** offline schema + verifier · a live attach is optional and is **not** claimed here  
**Does not place orders.** Does not score fills. Does not authorize live trading.

Priority 4 (tester provenance) is [TESTER-PROVENANCE.md](TESTER-PROVENANCE.md).
This is Priority 5: persist trade-transaction **identifiers** so a fill can be
audited or refused — instead of inferring state from a later snapshot alone.

Official AlgoBook notes that **OnTradeTransaction is asynchronous** and that a
**slow handler stalls the queue**. The EA copies request / order / deal /
position ids into a ring and returns. Writes happen on a timer.

Each attach is an **immutable session**: a fresh `session_id` directory, a
manifest that is never overwritten, and sequences that start at 1 in that
directory only. Queue overflow consumes a sequence and is persisted in
`overflow.json` plus an overflow terminal. The verifier requires contiguous
sequences and an exact `FxRegistryLookup` / `symbol_registry.resolve()` map.

## What is and is not proven

| Claim | Status |
|-------|--------|
| Schema `mt5-trade-journal/v1` loads | Proven (`tests/fixtures/trade_journal/offline_ok/`) |
| Duplicate deal id refuses | Proven |
| Deal without a position id refuses | Proven |
| Deal position missing from a present snapshot refuses | Proven |
| Secret keys (`password`, …) refuse | Proven |
| `OrderSend` in the EA / verifier / tests refuses | Proven by source grep |
| Empty broker / `Login=0` refuse | Proven |
| Sequence gap (`seq` 2 → 999) refuses | Proven (`test_sequence_gap_999_refuses`) |
| Restart / appended history (mixed `session_id` or seq reset) refuses | Proven |
| Overflow count without persisted terminals refuses | Proven |
| Exness / `EURUSD` (no exact registry map) refuses | Proven (`test_exness_eurusd_manifest_refuses`) |
| `FxCanonicalFromBrokerSymbolAny` fallback is absent | Proven by source grep |
| A live `OnTradeTransaction` attach on this machine | **Not claimed.** Offline tests only. |

Forming-bar gates are **not** required here (those belong to the parity package).
Unmapped symbols **are** refused (HIGH-4).

## How it works

```
InpBroker=vantage   # required; exact FxRegistryLookup or OnInit aborts
  → fresh Files/mt5_arch/journal/<session_id>/  (refuse overwrite)
  → OnTradeTransaction copies ids into a 256-slot ring (or RecordOverflow)
  → OnTimer appends JSONL + CSV + overflow.json in that session directory
  → optional sibling/parent account.json + positions.json (bridge snapshots)
  → Python verify: resolve() + contiguous seq + missing/duplicate deals fail closed
```

Resolution of the chart symbol uses `FxRegistryLookup` at **OnInit** only.
There is no `FxCanonicalFromBrokerSymbolAny` fallback. The handler does not
call `SymbolSelect`, history APIs, or the network.

## Files

| Path | Role |
|------|------|
| `mql5/Experts/TradeTransactionJournal.mq5` | Read-only diagnostic EA |
| `src/mt5_arch/trade_journal.py` | Platform-clean load / verify |
| `scripts/verify_trade_journal.py` | CLI wrapper |
| `tests/fixtures/trade_journal/offline_ok/` | Committed synthetic record |

## Commands

```bash
uv run python scripts/verify_trade_journal.py
uv run python scripts/verify_trade_journal.py tests/fixtures/trade_journal/offline_ok
uv run pytest tests/test_trade_journal.py
```

Optional live attach (one prefix; **does not place orders**):

1. `WINEPREFIX=~/.mt5-vantage ./scripts/18-install-forex-indicator.sh`
2. Compile `Experts/TradeTransactionJournal.mq5` (needs `FxSymbolRegistry.mqh`).
3. Attach to **one** chart. Set `InpBroker=vantage|fpmarkets|exness|wsf`.
4. `uv run python scripts/verify_trade_journal.py /path/to/MQL5/Files/mt5_arch/journal/<session_id>`

Never commit a live dump. Never put `MT5_PASSWORD` in the journal.

## Recorded fields

- Manifest: schema, source, **session_id**, broker, requested/canonical/broker_symbol, login, server
- Per event: seq, **session_id**, time, trans_type, request_id, order, deal, position, position_by, symbol, **overflow**
- `overflow.json`: dropped count and persisted overflow sequence numbers
- Optional correlation: bridge `account.json` login and `positions.json` tickets

## What this does not do

- Priority 6: article-intake gate.
- Live orders, Strategy Tester scoring, or a blended synthetic instrument.
- Prove that a deal was a good fill.
- Claim a live `OnTradeTransaction` run on this machine.
