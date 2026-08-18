# Forex MT5 stack — roadmap & decisions

## Why these next steps (not others)

| Option | Value | Cost | Verdict |
|--------|-------|------|---------|
| **HTF Pivots + Fib on MT5** | Matches your live TV/manual workflow; levels you already trade | Medium | **Do now** ✅ |
| **Signal logger EA (no orders)** | Proves `iCustom` path; CSV for review; zero blow-up risk | Low | **Do now** ✅ |
| EMA template polish | Already done (cloud, PDH, colors) | Done | Maintain |
| Full trading EA | Risk, sizing, prop rules, news | High | **Later** after signals prove useful |
| Port session-momentum z-score | Edge lives in cTrader Python today | High | Parallel track, not MT5-first |
| Auto-trade from Fib markers | Same as full EA | High | Only after logger paper stats |
| **US30/US100 session scalp overlay** | Cash-open ORB+VWAP+EMA observe on M5 | Medium | Overlay shipped; flatten replay PF below 1 — not a promote |

Principle: **visual parity with TV first → observe → automate read-only → only then trade.**

## What shipped (this wave)

```
mql5/
  Include/ForexUtils.mqh              # pips, sessions, pivots, EMA/ATR/RSI helpers
  Indicators/ForexIndicatorTemplate.mq5   # bias cloud + prior-day levels
  Indicators/ForexHtfPivotsFib.mq5        # ★ TV port: HTF pivots + Fib + confluence
  Experts/ForexSignalLogger.mq5           # iCustom → Print/CSV (never OrderSend)
  Mt5ArchBridge.mq5                       # existing file bridge
```

### Recommended chart layout

1. **Primary:** `ForexHtfPivotsFib` on **H1** (or M15) for EURUSD/GBPUSD/NZDCHF  
2. **Optional:** `ForexIndicatorTemplate` only if you want prior-day cloud bias alone  
3. **Logger:** `ForexSignalLogger` on same chart when you want a signal journal  

### Buffer contract (for agents / future EA)

| Indicator | Signal buffer | Extra |
|-----------|--------------:|-------|
| `ForexHtfPivotsFib` | **7** | 4=fib618, 5=fib786, 6=swingDir |
| `ForexIndicatorTemplate` | **8** | EMA cloud + PDH objects |

## Next waves (ordered)

### Wave B — Observe (1–2 weeks)
- Run HTF Fib on 2–3 pairs; save chart template  
- Logger CSV → review: did markers align with your discretionary entries?  
- Calibrate session hours / pivot left-right if levels feel early/late  

### Wave C — Bridge levels to Python
- Extend Mt5ArchBridge (or a small indicator file writer) to dump:  
  `pdh, pdl, fib618, fib786, swing_dir, last_signal` as JSON  
- `mt5-arch` CLI / agent can consume without Wine IPC  

### Wave D — Paper EA (still no live)
- EA: buffer 7 → log + optional *simulated* position state  
- ATR stop/target guide (same numbers as Pine strategy tester)  
- Hard: max spread, session, one trade per swing  

### Wave E — Live (only if Wave B–D green)
- Prop / account risk from your cTrader/FundedHive lessons  
- WSFmarkets path you already use for Mt5ArchBridge  

## Non-goals for MT5 right now
- Rebuilding full session-momentum z-score engine in MQL5  
- Market store / WebView features under Wine  
- MetaEditor as primary IDE (edit in repo → install script → F7)  

## Install

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/18-install-forex-indicator.sh
```
