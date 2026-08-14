# Strategy Tester provenance

**Status:** offline schema + wrapper · a live tester run is optional and is **not** claimed here  
**Does not place orders.** Does not score strategies. Does not authorize live trading.

Priority 3 (H1 sync audit) is [SYMBOL-SYNC-AUDIT.md](SYMBOL-SYNC-AUDIT.md).
This is Priority 4: record enough identity that a Strategy Tester run can be
reproduced or refused — instead of citing a profit factor with no build, broker,
or history.

Official tester docs note that **multi-currency** testing depends on available
**synchronized foreign-symbol history**. Provenance is the point: the record
says which terminal, which mapped symbol, which model/window, which file
hashes, and which history listing was present. It does not prove the calendars
match; that is Priority 3.

## What is and is not proven

| Claim | Status |
|-------|--------|
| Schema `mt5-tester-provenance/v1` loads | Proven (`tests/fixtures/tester_provenance/offline_ok/`) |
| Missing hashes / `Login=0` / empty broker refuse | Proven |
| Unresolved symbol (no suffix walk) refuses | Proven (`GOLD`, WSF `XAUUSD`) |
| `source=mql5_export` requires an existing report path | Proven |
| Secret keys (`password`, …) refuse | Proven |
| Wrapper calls `19-run` and requires `MT5_BROKER` / `InpBroker` | Proven by script grep + preflight subprocess |
| A live Strategy Tester job on this machine | **Not claimed.** Offline tests only. `KILL_EXISTING=1` would kill a running terminal |

## How it works

```
MT5_BROKER=vantage   # or InpBroker; required
  → registry.resolve(broker, requested)   # no suffix walk
  → scripts/19-run-htf-fib-backtest.sh <broker_symbol> …
  → hash INI / SET / .mq5 / .mqh / .ex5
  → history listing identity (Tester/bases then terminal bases)
  → provenance.json next to the tester report
```

Resolution is the explicit registry (`InpBroker` / `MT5_BROKER`).
`19-run` is unchanged: Login from `common.ini`, ASCII+CRLF `/config`,
UTF-16LE `.set`, `Expert=` bare name, `KILL_EXISTING` default 1.

## Files

| Path | Role |
|------|------|
| `scripts/20-run-htf-fib-backtest-provenance.sh` | Wrapper: resolve → call 19-run → write `provenance.json` |
| `src/mt5_arch/tester_provenance.py` | Platform-clean schema / hash / verify |
| `scripts/verify_tester_provenance.py` | CLI wrapper |
| `tests/fixtures/tester_provenance/offline_ok/` | Committed synthetic record (placeholder hashes) |

## Commands

```bash
uv run python scripts/verify_tester_provenance.py
uv run python scripts/verify_tester_provenance.py tests/fixtures/tester_provenance/offline_ok
uv run pytest tests/test_tester_provenance.py
```

Optional live run (one prefix; **kills `terminal64` unless `KILL_EXISTING=0`**):

```bash
export WINEPREFIX=~/.mt5-vantage
export MT5_BROKER=vantage
# review: this calls 19-run with KILL_EXISTING=1 by default
./scripts/20-run-htf-fib-backtest-provenance.sh XAUUSD H1 2024.01.01 2025.01.01
```

`SKIP_TESTER=1` records from existing INI/SET/EX5/report artifacts and does
**not** launch or kill the terminal. Verify still fail-closes if hashes or the
report path are missing (`source=mql5_export`).

Never commit a live dump. Never put `MT5_PASSWORD` in `provenance.json`.

## Recorded fields

- Terminal name/path, PE file version / build, Wine version
- Broker, account login (not 0), server, inferred account type
- Requested / canonical / `broker_symbol` from the registry
- Tester expert, period, model (0–4), date window, deposit, leverage
- SHA-256 of tester INI, `.set`, `ForexHtfFibTester.mq5`, `ForexUtils.mqh`, compiled EX5
- History directory listing hash (not bar contents)
- Costs: spread mode, `InpMaxSpreadPips`, `InpSlippagePoints` (commission unknown)
- Tester report path; optional `PARITY_TRACE` / `SYNC_AUDIT` paths

## What this does not do

- Priority 5: `OnTradeTransaction` journal.
- Priority 6: article-intake gate.
- Live orders, fuzzy symbol matching, or a blended synthetic instrument.
- Prove that a tester profit factor is an edge.
