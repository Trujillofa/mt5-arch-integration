# OnTradeTransaction journal

**Status:** offline schema + verifier · a live attach is optional and is **not** claimed here  
**Does not place orders.** Does not score fills. Does not authorize live trading.

Priority 4 (tester provenance) is [TESTER-PROVENANCE.md](TESTER-PROVENANCE.md).
This is Priority 5: persist trade-transaction **identifiers** so a fill can be
audited or refused — instead of inferring state from a later snapshot alone.

Official AlgoBook notes that **OnTradeTransaction is asynchronous** and that a
**slow handler stalls the queue**. The EA copies request / order / deal /
position ids into a ring and returns. Writes happen on a timer.

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
| A live `OnTradeTransaction` attach on this machine | **Not claimed.** Offline tests only. |

Forming-bar and unmapped-symbol gates are **not** required here (those belong
to parity / registry packages).

## How it works

```
InpBroker=vantage   # required
  → OnTradeTransaction copies trans/request/result ids into a 256-slot ring
  → OnTimer appends JSONL + CSV under MQL5/Files/mt5_arch/journal/
  → optional sibling/parent account.json + positions.json (bridge snapshots)
  → Python verify: missing / duplicate / unexpected transitions fail closed
```

Resolution of the chart symbol uses `FxRegistryLookup` at **OnInit** only.
The handler does not call `SymbolSelect`, history APIs, or the network.

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
4. `uv run python scripts/verify_trade_journal.py /path/to/MQL5/Files/mt5_arch/journal`

Never commit a live dump. Never put `MT5_PASSWORD` in the journal.

## Recorded fields

- Manifest: schema, source, broker, requested/canonical/broker_symbol, login, server
- Per event: seq, time, trans_type, request_id, order, deal, position, position_by, symbol
- Optional correlation: bridge `account.json` login and `positions.json` tickets

## What this does not do

- Priority 6: article-intake gate.
- Live orders, Strategy Tester scoring, or a blended synthetic instrument.
- Prove that a deal was a good fill.
- Claim a live `OnTradeTransaction` run on this machine.
