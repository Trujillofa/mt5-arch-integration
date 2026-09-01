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
| **US30/US100 session scalp overlay** | Cash-open ORB+VWAP+EMA observe on M5; logger buffer 8; live-safe M5 export | Medium | Overlay v1.41 (Asia/London H/L observe). Screens stay Python-only. **promote=no** |

Principle: **visual parity with TV first → observe → automate read-only → only then trade.**

## What shipped (this wave)

```
mql5/
  Include/ForexUtils.mqh              # pips, sessions, pivots, EMA/ATR/RSI helpers
  Include/IndexSessionUtils.mqh       # US-index DST clock + point spread
  Include/IndexM5Export.mqh           # live-safe US100/US30 M5 dump
  Indicators/ForexIndicatorTemplate.mq5   # bias cloud + prior-day levels
  Indicators/ForexHtfPivotsFib.mq5        # ★ TV port: HTF pivots + Fib + confluence
  Indicators/UsIndexSessionScalp.mq5      # US30/US100 cash-open scalp overlay
  Indicators/BtcTrendPullback.mq5         # BTCUSD H4/H1 pullback
  Experts/ForexSignalLogger.mq5           # iCustom → Print/CSV (never OrderSend)
  Scripts/ExportUsIndexM5.mq5             # dump without killing the terminal
  Mt5ArchBridge.mq5                       # existing file bridge
```

### Recommended chart layout

1. **Primary FX/gold:** `ForexHtfPivotsFib` on **H1** (or M15) for EURUSD/GBPUSD/NZDCHF / XAUUSD
2. **US100 / US30 M5 (or M15):** `UsIndexSessionScalp` — observe only; [MT5-INTEGRATION-CAPABILITIES.md](MT5-INTEGRATION-CAPABILITIES.md)
3. **Optional:** `ForexIndicatorTemplate` only if you want prior-day cloud bias alone
4. **Logger:** `ForexSignalLogger` on the same chart (`UsIndexSessionScalp` → buffer **8**, `InpMaxSpreadPips=0`)

### Buffer contract (for agents / future EA)

Authoritative tables live in [mql5/README.md](../mql5/README.md). Do not use older Fib-at-7 notes.

| Indicator | Signal buffer | Extra |
|-----------|--------------:|-------|
| `ForexHtfPivotsFib` | **8** | 5=fib618, 6=fib786, 7=swingDir |
| `ForexIndicatorTemplate` | **8** | EMA cloud + PDH objects |
| `UsIndexSessionScalp` | **8** | 2=VWAP, 3–4=OR, 9=ATR |
| `BtcTrendPullback` | **7** | 6=HTF bias |

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
