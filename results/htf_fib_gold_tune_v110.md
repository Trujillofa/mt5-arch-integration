# ForexHtfFibTester v1.20 — Gold (XAUUSD) research + diagnostics

> Supersedes v1.10 notes. Indicator **ForexHtfPivotsFib v1.32** required.

## Why gold, not BTC?

| | **XAUUSD (recommended)** | **BTCUSD** |
|--|--------------------------|------------|
| Indicator | ForexHtfPivotsFib (this EA) | **BtcTrendPullback** (separate) |
| Structure | Clean H4/D Fib swings | 24/7, different regime |
| Spread filter | Pip helper supports XAU | Pip math wrong / huge |
| Lot risk | 0.01 sensible | 0.01 still volatile |
| History | Broker XAU H1 fine after download | Long local history but wrong stack |

Use **gold** for HTF Fib EA tests. BTC later via a dedicated EA on `BtcTrendPullback` buffer.

## What changed vs EURUSD v1.00

| Param | Old (FX) | New (gold default) | Why |
|-------|----------|--------------------|-----|
| Lots | 0.10 | **0.01** | 0.1 gold + ATR stop is large $ risk |
| SL ATR | 1.5 | **2.0** | Gold noise |
| TP ATR | 2.0 | **3.0** | ~1.5R |
| Max spread pips | 2.5 | **80** | XAU “pips” ≠ FX; avoid blocking all trades |
| Slippage pts | 30 | **50** | Wider |
| RSI long max | 35 (ind default) | **42** | More signals |
| RSI short min | 65 | **58** | More signals |
| RSI-MA filter | on | **off** | Was ~1 trade/year on EUR |
| Magic | 26080501 | **26080502** | New series |
| iCustom | defaults only | **full param pass** | EA knobs actually affect signals |

## GUI Strategy Tester (do this in Vantage)

1. Navigator → Experts → **ForexHtfFibTester** — right-click **Refresh** if version still 1.00.
2. **Ctrl+R** Strategy Tester.
3. Settings:
   - Expert: `ForexHtfFibTester`
   - Symbol: **XAUUSD**
   - Period: **H1**
   - Dates: **2024.01.01 → 2025.01.01** (or 2023–2025 if history allows)
   - Model: **1 minute OHLC** (or Every tick if patient)
   - Deposit: 10000, leverage 1:100
4. Inputs tab: confirm v1.10 gold defaults (or flip `InpUseRsiMaFilter=true` for stricter).
5. **Start**. Wait for history download if first XAU run.
6. Journal: look for `ForexHtfFibTester v1.10 ON XAUUSD` and `OnTester summary trades=…`.

## Optional A/B on Inputs

- **Strict:** RSI 35/65 + `InpUseRsiMaFilter=true` (few trades, higher quality)
- **Loose (default):** RSI 42/58 + filter off (more sample size)
- **Swing mode:** `InpTradingMode=SWING` (50/200 + Daily Fib) on H4 chart period

## After run

Ask to “check logs” — agent log under  
`Tester/Agent-127.0.0.1-3001/logs/YYYYMMDD.log`

## v1.20 research + diagnostics

### New inputs
| Input | Gold research default | Meaning |
|-------|----------------------|---------|
| `InpRequireGoldenZone` | **false** | Skip Fib 61.8–78.6 (main zero-trade cause) |
| `InpRequireBiasFilter` | **true** | Keep EMA200 regime |
| `InpDiagVerbose` | true | Journal `DIAG[OnTester]` funnel line |

### DIAG funnel line (Journal)
```
DIAG[OnTester] bars=… fibValid=… swing!=0=… zoneL/S=… regimeL/S=… rsiL/S=… sigL/S=… entryOK/fail=…
```
Read left→right: first near-zero count is the bottleneck.

### GUI retest
1. Refresh Experts + Indicators (need v1.20 EA + v1.32 ind).
2. **Single** · XAUUSD · H1 · 2024→2025.
3. Inputs: Defaults (zone OFF, bias ON, spread 0, lots 0.01).
4. Start → Journal → search `DIAG[OnTester]` and `v1.20 ON`.
5. Optional A/B: set `InpRequireGoldenZone=true` for production-like strictness.
