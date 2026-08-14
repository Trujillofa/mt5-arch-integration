# Multi-symbol H1 synchronization audit

**Status:** offline schema + comparison rules · live MT5-versus-package is optional
**Does not place orders.** Does not score strategies. Does not replace
XAU/EUR/GBP with an averaged synthetic symbol.

Priority 2 (explicit broker symbol maps) is [SYMBOL-REGISTRY.md](SYMBOL-REGISTRY.md).
This is Priority 3: independently check that a terminal's H1 calendars match
the packaged intersection — per canonical, fail-closed.

## What is and is not proven

| Claim | Status |
|-------|--------|
| Dump schema `mt5-symbol-sync-audit/v1` loads | Proven (`tests/fixtures/symbol_sync_audit/offline_ok/`) |
| `mql5_export` must list every mapped canonical for that broker | Proven (`test_mql5_export_missing_mapped_canonical_fails`) |
| Missing / mismatched first-last / wrong intersection refuse | Proven |
| Missing timestamps or differing bar counts omit a symbol from the joint set | Proven (`test_differing_count_missing_timestamp_refuses`) |
| Forming last bar without `last_forming` refuses | Proven |
| Unmapped `GOLD` without `error=not_in_registry` refuses | Proven |
| Optional package snapshot first/last/count/intersection compare | Proven against the committed synthetic package JSON |
| Live MT5 history vs a published research package | **Not claimed** until a real dump is verified |
| Weekend hourly gaps are a hard fail | **No.** `n_missing_vs_hourly` is reported, not gated |

The packaged intersection calendar (see
`scripts/build_multi_instrument_data_readiness.py` `common_window`) is the
timestamp-set AND of the develop series. This audit does not import that
script. When `--package` is given, it compares fields only.

## How it works

```
InpBroker=vantage
  → FxResolveSymbol(canonical) for each mapped name
  → CopyRates(H1): first/last, count, spread>0, hourly holes, timestamps
  → joint = closed-timestamp intersection (forming last bar excluded)
  → Python: registry floor + recompute intersection + optional package compare
```

Resolution is the explicit registry. No suffix walk. No first-match.

## Files

| Path | Role |
|------|------|
| `mql5/Scripts/ExportSymbolSyncAudit.mq5` | Read-only live dump |
| `src/mt5_arch/symbol_sync_audit.py` | Platform-clean verifier |
| `scripts/verify_symbol_sync_audit.py` | CLI wrapper |
| `tests/fixtures/symbol_sync_audit/` | Committed synthetic dump + package snapshot |

## Commands

```bash
uv run python scripts/verify_symbol_sync_audit.py
uv run python scripts/verify_symbol_sync_audit.py tests/fixtures/symbol_sync_audit/offline_ok \
  --package tests/fixtures/symbol_sync_audit/package_ok.json
uv run pytest tests/test_symbol_sync_audit.py
```

Optional live dump (one prefix only; set `InpBroker` to that broker):

1. `WINEPREFIX=~/.mt5-vantage ./scripts/18-install-forex-indicator.sh`
2. Compile `ExportSymbolSyncAudit.mq5`.
3. Run the script on a chart.
4. `uv run python scripts/verify_symbol_sync_audit.py /path/to/dump`

If a readiness/package JSON is available, pass `--package` to compare
`n_rows_h1` / first / last / `n_intersection_timestamps`. Do not treat equal
counts as proof the calendars match — timestamps are required.

## What this does not do

- Priority 4: Strategy Tester provenance wrapper.
- Priority 5: `OnTradeTransaction` journal.
- Priority 6: article-intake gate.
- Live orders, fuzzy symbol matching, or a blended synthetic instrument.
