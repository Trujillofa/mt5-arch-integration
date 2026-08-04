# MQL5 sources (mt5-arch-integration)

| File | Role |
|------|------|
| `Include/ForexUtils.mqh` | Pips, sessions, spread, pure EMA/ATR/RSI, pivot helpers |
| `Indicators/ForexIndicatorTemplate.mq5` | EMA cloud + prior-day H/L/O + RSI template signals |
| `Indicators/ForexHtfPivotsFib.mq5` | **FX/gold primary:** confirmed HTF pivots + directional Fib |
| `Indicators/BtcTrendPullback.mq5` | **BTCUSD primary:** H4 bias + H1 EMA pullback reclaim (ATR guides) |
| `Experts/ForexSignalLogger.mq5` | Log-only EA (`iCustom` → Print/CSV, **no orders**) |
| `Mt5ArchBridge.mq5` | File bridge EA for Linux Python |

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

## Design sources

| Repo source | Used for |
|-------------|----------|
| `manual-trading-agent` Pine HTF Fib | Pivot confirm, swing machine, golden zone, RSI confluence |
| `ForexIndicatorTemplate` | Cloud/colors/panel Wine lessons |
| `ctrader` session-momentum | Spread gate philosophy (logger filter) |
| `crypto-agent` TrendPullback | BTC EMA/RSI/MACD reclaim grammar (`BtcTrendPullback`) |
