# Path A — Real HTF Fib backtest (recommended)

## Why this path

Research RSI (zone OFF) proved the tester pipeline works (150 trades, PF 0.91) but is **not** the Fib strategy.  
Path A restores **golden-zone Fib confluence** so Strategy Tester measures the real edge.

## What shipped

| Component | Version | Change |
|-----------|---------|--------|
| ForexHtfPivotsFib | **1.40** | Chrono `CopyRates`, historical fib snaps, relaxed pivot machine, per-bar FibAt |
| ForexHtfFibTester | **1.30** | Defaults: **zone ON**, Fib signal primary, live-trade blocked unless allowed |

## GUI retest (Single only — not Visualize)

1. Navigator → Refresh Experts + Indicators  
2. **Ctrl+R** → Expert **ForexHtfFibTester**  
3. Symbol **XAUUSD**, Period **H1**, dates **2024.01.01 → 2025.01.01**  
4. Model: **1 minute OHLC**  
5. Inputs → **Defaults** (or confirm):
   - `InpRequireGoldenZone` = **true**
   - `InpRequireBiasFilter` = **true**
   - `InpResearchFallback` = **false**
   - `InpRsiLongMax` / `ShortMin` = 40 / 60
   - `InpUseRsiMaFilter` = false
   - lots 0.01, SL 2, TP 3, maxSpread **0**
   - `InpAllowLiveTrading` = false  
6. **Start**  
7. Journal must show:
   - `ForexHtfPivotsFib rebuild n=… pivots=… snaps=… swingDir=±1`
   - `ForexHtfFibTester v1.30 … zone=ON`
   - `DIAG … swing!=0>0 fibValid>0 sigL/S≠0/0`

## Success criteria

| Check | Good |
|-------|------|
| snaps > 0 | Fib history built |
| swing!=0 / fibValid | non-zero in DIAG |
| sigL/S | non-zero (real Fib signals) |
| trades | any count OK; compare vs research RSI run |

## Live charts

- **Do not** leave this EA on live charts for trading (`InpAllowLiveTrading=false`).  
- Chart visuals: indicator only.  
- One **Mt5ArchBridge** only.
