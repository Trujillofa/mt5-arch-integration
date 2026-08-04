# MQL5 sources (mt5-arch-integration)

| File | Role |
|------|------|
| `Include/ForexUtils.mqh` | Pips, sessions, spread, pure EMA/ATR/RSI, pivot helpers |
| `Indicators/ForexIndicatorTemplate.mq5` | EMA cloud + prior-day H/L/O + RSI template signals |
| `Indicators/ForexHtfPivotsFib.mq5` | **Primary:** confirmed HTF pivots + directional Fib (TV port) |
| `Experts/ForexSignalLogger.mq5` | Log-only EA (`iCustom` → Print/CSV, **no orders**) |
| `Mt5ArchBridge.mq5` | File bridge EA for Linux Python |

Roadmap: [docs/FOREX-MT5-ROADMAP.md](../docs/FOREX-MT5-ROADMAP.md)

## Install into Wine MT5

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/18-install-forex-indicator.sh
```

MetaEditor **F7** compile order:

1. `Indicators/ForexHtfPivotsFib.mq5`
2. `Indicators/ForexIndicatorTemplate.mq5` (optional)
3. `Experts/ForexSignalLogger.mq5` (optional)

## Chart recipe (best default)

| Setting | Value |
|---------|--------|
| Symbol | EURUSD / GBPUSD / major FX |
| TF | **H1** or M15 (must be ≤ H4 for 4H pivot layer) |
| Indicator | **ForexHtfPivotsFib** |
| Look for | Golden zone (61.8–78.6), EMA200 filter, lime/red markers |

### ForexHtfPivotsFib buffers (`iCustom`)

| Index | Content |
|------:|---------|
| 0 | EMA50 |
| 1 | EMA200 |
| 2 | Long arrow |
| 3 | Short arrow |
| 4 | Fib 61.8 |
| 5 | Fib 78.6 |
| 6 | Swing direction (+1/−1) |
| **7** | **Signal (+1/−1/0)** |

```mql5
double sig[];
ArraySetAsSeries(sig, true);
CopyBuffer(handle, 7, 1, 1, sig);  // last closed bar
```

### ForexIndicatorTemplate buffers

| Index | Content |
|------:|---------|
| 0–3 | Bull/bear cloud + EMAs |
| 6–7 | Long/short arrows |
| **8** | **Signal** |

### ForexSignalLogger

- Inputs: indicator name (`ForexHtfPivotsFib` or `ForexIndicatorTemplate`), buffer index (`7` or `8`)
- Writes `MQL5/Files/forex_signals/<SYMBOL>_<TF>.csv`
- **Never** calls `OrderSend`

## Design sources

| Repo source | Used for |
|-------------|----------|
| `manual-trading-agent` Pine HTF Fib | Pivot confirm, swing machine, golden zone, RSI confluence |
| `ForexIndicatorTemplate` | Cloud/colors/panel Wine lessons |
| `ctrader` session-momentum | Spread gate philosophy (logger filter) |
