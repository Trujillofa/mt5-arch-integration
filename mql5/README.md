# MQL5 sources (mt5-arch-integration)

| File | Role |
|------|------|
| `Include/ForexUtils.mqh` | Pips, sessions, spread, pure EMA/ATR/RSI, pivot helpers |
| `Indicators/ForexIndicatorTemplate.mq5` | EMA cloud + prior-day H/L/O + RSI template signals |
| `Indicators/ForexHtfPivotsFib.mq5` | **FX/gold primary:** HTF pivots + Fib — **[How to use](../docs/HOWTO-HTF-FIB.md)** |
| `Indicators/BtcTrendPullback.mq5` | **BTCUSD primary:** H4 bias + H1 EMA pullback reclaim (ATR guides) |
| `Experts/ForexSignalLogger.mq5` | Log-only EA (`iCustom` → Print/CSV, **no orders**) |
| `Experts/ForexHtfFibTester.mq5` | **Strategy Tester EA** — buffer 8 + ATR SL/TP |
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
| 8 | RSI |
| 9 | RSI-MA |

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
