# Broker symbol capability registry

**Status:** explicit maps only · live capability dump is optional  
**Does not place orders.** Does not score strategies.

Priority 1 (MQL5 ↔ Python HTF Fib parity) is done. This is Priority 2: stop
resolving `XAUUSD` by walking `m`, `.r`, `.m`, `#`, `pro` and taking the first
`SymbolSelect` success.

## What is and is not proven

| Claim | Status |
|-------|--------|
| `(broker, canonical) → broker_symbol` is explicit | Proven against `config/symbols/registry.json` |
| Unknown broker / GOLD / WSF XAUUSD refuses | Proven in `tests/test_symbol_registry.py` |
| Duplicate `broker_symbol` on one broker refuses at load | Proven |
| MQL5 include lockstep with the JSON | Proven (`render_mql5_include`) |
| Suffix walk removed from bridge / history exporter / S/R strip | Proven by source grep |
| Live `SymbolSelect` + digits/point/contract/bars on every broker | **Not claimed** until a capability dump is verified |
| `source=mql5_export` must list every mapped canonical | Proven (`test_capability_mql5_export_missing_mapped_canonical_fails`) |
| WSF mappings | **None.** Broker is listed so resolve fails closed |
| Exness beyond `XAUUSD → XAUUSDm` | **Not claimed** |
| `GOLD` ↔ `XAUUSD` | **Not mapped** |

Evidence for the shipped maps: [research/PHASE0-DISCOVERY.md](research/PHASE0-DISCOVERY.md)
(Vantage bare names, FP `XAUUSD.r` / `BTCUSD`) and
`results/xau_bridge_deploy_exness.md` (heartbeat `XAUUSDm`).

## How it works

```
canonical XAUUSD
  vantage  → XAUUSD
  fpmarkets → XAUUSD.r
  exness   → XAUUSDm
  wsf      → refuse
```

Python (`mt5_arch.symbol_registry.resolve`) and MQL5 (`FxResolveSymbol`) share
that table. The include is generated — do not hand-edit it:

```bash
uv run python scripts/verify_symbol_registry.py --write-include
```

`FxResolveSymbol` then `SymbolSelect`s **only** the mapped name. It does not
try suffixes. `InpBroker` is required on `Mt5ArchBridge` and the history
exporter (`vantage|fpmarkets|exness|wsf`).

Inverse lookup (`FxCanonicalFromBrokerSymbolAny`) is used so S/R CSV rows
tagged `XAUUSDm` still match an `XAUUSD.r` chart **when both names are in the
registry**. Unmapped names are not stripped.

## Files

| Path | Role |
|------|------|
| `config/symbols/registry.json` | Source of truth |
| `src/mt5_arch/symbol_registry.py` | Load / resolve / verify / generate include |
| `mql5/Include/FxSymbolRegistry.mqh` | Generated shared include |
| `mql5/Scripts/ExportSymbolCapabilities.mq5` | Read-only live dump |
| `scripts/verify_symbol_registry.py` | Lockstep + optional dump check |
| `tests/fixtures/symbol_registry/offline_ok/` | Committed synthetic dump |

## Commands

```bash
uv run mt5-arch resolve vantage XAUUSD --json
uv run mt5-arch resolve fpmarkets XAUUSD --json
uv run python scripts/verify_symbol_registry.py
uv run pytest tests/test_symbol_registry.py
```

Optional live dump (Vantage only; set `InpBroker=vantage`):

1. `WINEPREFIX=~/.mt5-vantage ./scripts/18-install-forex-indicator.sh`
2. Compile `FxSymbolRegistry.mqh` consumers (bridge, exporter, capability script).
3. Run `ExportSymbolCapabilities` on a chart.
4. `uv run python scripts/verify_symbol_registry.py /path/to/dump`

With `MT5_BROKER=fpmarkets` (`BROKER` is still accepted), `mt5-arch symbols XAUUSD`
looks up the bridge row named `XAUUSD.r`. Without a broker env, the CLI stays
exact-name (old behaviour).

## What this does not do

- Priority 3: MT5-versus-package synchronization audit — **separate package**:
  [SYMBOL-SYNC-AUDIT.md](SYMBOL-SYNC-AUDIT.md).
- Priority 4: Strategy Tester provenance wrapper — **separate package**:
  [TESTER-PROVENANCE.md](TESTER-PROVENANCE.md).
- Priority 5: `OnTradeTransaction` journal — **separate package**:
  [TRADE-JOURNAL.md](TRADE-JOURNAL.md).
- Fuzzy substring matching from the MQL5.com broker-agnostic article.
