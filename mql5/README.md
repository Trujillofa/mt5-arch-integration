# MQL5 sources (mt5-arch-integration)

| File | Role |
|------|------|
| `Include/ForexUtils.mqh` | Pips, sessions, spread, pure EMA/ATR/RSI, pivot helpers |
| `Indicators/ForexIndicatorTemplate.mq5` | EMA cloud + prior-day H/L/O + RSI template signals |
| `Indicators/ForexHtfPivotsFib.mq5` | **FX/gold primary:** HTF pivots + Fib — **[How to use](../docs/HOWTO-HTF-FIB.md)** |
| `Indicators/BtcTrendPullback.mq5` | **BTCUSD primary:** H4 bias + H1 EMA pullback reclaim (ATR guides) |
| `Experts/ForexSignalLogger.mq5` | Log-only EA (`iCustom` → Print/CSV, **no orders**) |
| `Experts/ForexHtfFibTester.mq5` | **Strategy Tester EA** — EA-native Fib + ATR SL/TP (not iCustom buffer 8) |
| `Scripts/ExportHtfFibParityFixture.mq5` | Read-only MQL5 ↔ Python parity dump (no orders) |
| `Include/FxSymbolRegistry.mqh` | Generated explicit broker → symbol maps (no suffix walk) |
| `Scripts/ExportSymbolCapabilities.mq5` | Read-only symbol capability dump (no orders) |
| `Mt5ArchBridge.mq5` | File bridge EA for Linux Python (v1.23) |
| `Files/forex_sr_levels.csv` | Generated S/R level table — see below |

### Mt5ArchBridge symbols (v1.23)

`InpBroker` is **required** (`vantage|fpmarkets|exness|wsf`).
`InpSymbols` / `InpHistorySymbol` use **canonical** names (`EURUSD,GBPUSD,USDJPY,XAUUSD,BTCUSD`).
`FxResolveSymbol` maps them through `config/symbols/registry.json` and `SymbolSelect`s only that name — no suffix walk.
`symbols.json` and candle filenames still use the **resolved** broker name (e.g. `XAUUSD.r`).
See [docs/SYMBOL-REGISTRY.md](../docs/SYMBOL-REGISTRY.md).

Roadmap: [docs/FOREX-MT5-ROADMAP.md](../docs/FOREX-MT5-ROADMAP.md) · BTC design: [docs/research/BTC-INDICATOR-DESIGN.md](../docs/research/BTC-INDICATOR-DESIGN.md)

## Install into Wine MT5

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/18-install-forex-indicator.sh
```

MetaEditor **F7** compile order:

1. `Indicators/ForexHtfPivotsFib.mq5`
2. `Indicators/BtcTrendPullback.mq5`
3. `Indicators/ForexIndicatorTemplate.mq5` (optional)
4. `Experts/ForexSignalLogger.mq5` (optional)
5. `Scripts/ExportHtfFibParityFixture.mq5` (optional; MQL5 ↔ Python dump)
6. `Scripts/ExportSymbolCapabilities.mq5` (optional; broker symbol dump)

## Chart recipe — FX / gold

| Setting | Value |
|---------|--------|
| Symbol | EURUSD / GBPUSD / XAUUSD (or `XAUUSD.r` on FP) |
| TF | **H1** or M15 (must be ≤ H4 for 4H pivot layer) |
| Indicator | **ForexHtfPivotsFib** |
| Look for | Golden zone (61.8–78.6), EMA200 filter, lime/red markers |

## Chart recipe — BTC

| Setting | Value |
|---------|--------|
| Symbol | **BTCUSD** |
| TF | **H1** (H4 used internally for bias) |
| Indicator | **BtcTrendPullback** |
| Logger | `InpIndicatorName=BtcTrendPullback`, buffer **7**, `InpMaxSpreadPips=0` |
| Look for | EMA50/200 stack, pullback reclaim arrows, ATR bands (price, not pips) |

### Trading mode (both indicators)

| Mode | EMAs | Sessions | Spread | Fib | Chart |
|------|------|----------|--------|-----|-------|
| **INTRADAY** | **20 / 50** + bias **200** | London/NY/overlap | max 2.5 p | 4H pivots | M15–H1 |
| **SWING** | **50 / 200** (bias = 200) | off | off | Daily pivots | H4–D1 |

- Cloud / timing = fast vs slow
- Signals also require **close vs EMA bias (200)** when mode uses bias filter
- `InpManualEmaOverride` / `InpManualOverride` locks periods to the input fields

Signal buffers: **HTF Fib = 8**, **Template = 9**.

### RSI + RSI-MA (both indicators)

| Input | Default | Role |
|-------|---------|------|
| `InpRsiPeriod` | 14 | RSI length |
| `InpRsiMaPeriod` | 14 | MA of RSI (signal line) |
| `InpRsiMaMethod` | SMA | SMA or EMA on RSI |
| `InpUseRsiMaFilter` | true | Long needs RSI > RSI-MA; short RSI < RSI-MA |

Panel shows `RSI` and `RSI MA` with above/below tag.

### Imported S/R levels (ForexHtfPivotsFib v1.43+)

`scripts/tpl_to_sr_levels.py` converts the hand-drawn `OBJ_HLINE` zones of the manual
`plantillas/*.tpl` chart templates into `Files/forex_sr_levels.csv`, which the indicator
reads **at runtime** (no recompile). Relevance = the timeframe the line was drawn on:

| Tier | Colour | Drawn on |
|------|--------|----------|
| HIGH | Yellow | MN / W1 / D1 / H4 |
| MED | White | H1 / M30 / M15 |
| LOW | Blue | M5 / M1 |

```bash
python3 scripts/tpl_to_sr_levels.py       # PLANTILLAS_DIR=... to point elsewhere
./scripts/18-install-forex-indicator.sh   # copies CSV to MQL5\Files + Common\Files
```

Static snapshot — regenerate after re-drawing zones. Full notes:
[docs/HOWTO-HTF-FIB.md §5.2b](../docs/HOWTO-HTF-FIB.md).

### ForexHtfPivotsFib buffers (`iCustom`)

Authoritative map (v1.42+). Do not use the old signal-at-7 table.
Parity harness: [docs/MQL5-PYTHON-PARITY.md](../docs/MQL5-PYTHON-PARITY.md).

| Index | Content |
|------:|---------|
| 0 | EMA fast |
| 1 | EMA slow |
| 2 | EMA bias |
| 3 | Long arrow |
| 4 | Short arrow |
| 5 | Fib 61.8 |
| 6 | Fib 78.6 |
| 7 | Swing direction (+1/−1) |
| **8** | **Signal (+1/−1/0)** |
| 9 | RSI |
| 10 | RSI-MA |

```mql5
double sig[];
ArraySetAsSeries(sig, true);
CopyBuffer(handle, 8, 1, 1, sig);  // last closed bar
```

### ForexIndicatorTemplate buffers

| Index | Content |
|------:|---------|
| 0–3 | Bull/bear cloud + EMAs |
| 6–7 | Long/short arrows |
| **8** | **Signal** |

### BtcTrendPullback buffers (`iCustom`)

| Index | Content |
|------:|---------|
| 0 | EMA50 |
| 1 | EMA200 |
| 2 | ATR lower guide |
| 3 | ATR upper guide |
| 4 | Long arrow |
| 5 | Short arrow |
| 6 | HTF bias (+1/−1/0) |
| **7** | **Signal (+1/−1/0)** |

### ForexSignalLogger

- Inputs: indicator name (`ForexHtfPivotsFib`, `BtcTrendPullback`, or `ForexIndicatorTemplate`), buffer (`7` or `8`)
- BTC: set **`InpMaxSpreadPips=0`** (pip gate is FX-oriented)
- Writes `MQL5/Files/forex_signals/<SYMBOL>_<TF>.csv`
- **Never** calls `OrderSend`
- Parity dump: `Scripts/ExportHtfFibParityFixture.mq5` →
  [docs/MQL5-PYTHON-PARITY.md](../docs/MQL5-PYTHON-PARITY.md)

## Design sources

| Repo source | Used for |
|-------------|----------|
| `manual-trading-agent` Pine HTF Fib | Pivot confirm, swing machine, golden zone, RSI confluence |
| `ForexIndicatorTemplate` | Cloud/colors/panel Wine lessons |
| `ctrader` session-momentum | Spread gate philosophy (logger filter) |
| `crypto-agent` TrendPullback | BTC EMA/RSI/MACD reclaim grammar (`BtcTrendPullback`) |
