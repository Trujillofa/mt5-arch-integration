# Wave B — Observe checklist (Vantage)

**Goal:** Run HTF Fib + optional signal logger for 1–2 weeks. **No OrderSend.**  
**Broker:** Vantage (`~/.mt5-vantage`) — majors + `XAUUSD` trade_mode FULL.

Installed & compiled (2026-08-04+):

- `Indicators/ForexHtfPivotsFib.ex5` ← FX/gold primary
- `Indicators/BtcTrendPullback.ex5` ← **BTCUSD primary**
- `Indicators/ForexIndicatorTemplate.ex5` ← optional
- `Experts/ForexSignalLogger.ex5` ← log-only
- `Experts/Mt5ArchBridge.ex5` v1.04

Design: [BTC-INDICATOR-DESIGN.md](BTC-INDICATOR-DESIGN.md)

---

## Chart setup (do in MT5 UI)

### FX / gold — **EURUSD, GBPUSD, USDJPY, XAUUSD**

| Setting | Value |
|---------|--------|
| Timeframe | **H1** (or M15) |
| Indicator | Navigator → Indicators → **ForexHtfPivotsFib** |
| Look for | Golden zone 61.8–78.6, EMA200 filter, lime/red markers |
| Optional EA | **ForexSignalLogger** name=`ForexHtfPivotsFib` buffer **7** |
| Template | Save chart template after first chart looks right |

### BTC — **BTCUSD**

| Setting | Value |
|---------|--------|
| Timeframe | **H1** |
| Indicator | Navigator → Indicators → **BtcTrendPullback** |
| Look for | EMA50/200, ATR bands, lime/red reclaim arrows |
| Optional EA | **ForexSignalLogger** name=`BtcTrendPullback` buffer **7**, **MaxSpreadPips=0** |
| Bridge | Ensure `Mt5ArchBridge` `InpSymbols` includes `BTCUSD` |

**Do not** attach a trading EA that places orders.

### Logger CSV path (Wine)

```
~/.mt5-vantage/drive_c/Program Files/Vantage International MT5/MQL5/Files/forex_signals/
```

Files look like `EURUSD_H1.csv` (see logger inputs).

---

## Daily / weekly review

- [ ] Markers align with discretionary entries you would take?
- [ ] Too many signals off-session / high spread?
- [ ] Gold (XAUUSD) levels feel early/late vs TV?
- [ ] Note server hours (≈ UTC+3 on 2026-08-04) when calibrating sessions

After ~1–2 weeks of notes → Wave C (JSON levels into Python bridge).

---

## Optional: finish BTC bridge export

Re-attach **Mt5ArchBridge** so Inputs include:

`EURUSD,GBPUSD,USDJPY,USDCHF,XAUUSD,XAUUSD.r,BTCUSD`

Then:

```bash
set -a; source config/brokers/vantage.env; set +a
uv run mt5-arch symbols BTCUSD --json
uv run mt5-arch candles BTCUSD --tf H1 --count 5 --json
```

---

## Safety

- Logger and bridge: **read-only** (no OrderSend).
- Keep discretionary risk separate; open NZDCHF/DJ30 positions are not part of this observe path.
- No live algo until Wave D/E after paper expectancy.
