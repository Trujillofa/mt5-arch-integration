# How to use: ForexHtfPivotsFib

**Indicator:** `MQL5/Indicators/ForexHtfPivotsFib.mq5`  
**Version covered:** 1.42+  
**Role:** Primary **forex** visual / signal tool — confirmed higher-timeframe pivots, directional Fibonacci, EMA regime, RSI + RSI-MA confluence.  
**Not an EA:** does not place orders. Optional journal via `ForexSignalLogger`.

Port of the TradingView stack in `manual-trading-agent` (`tradingview_pivot_rsi_ema.pine` / HTF Fib strategy ideas).

---

## 1. What it does (one screen)

| Layer | What you see | Purpose |
|-------|----------------|---------|
| **4H / Daily pivots** | Horizontal high/low lines | Confirmed swing structure (non-repaint after `right` bars) |
| **Directional Fib** | 50 / 61.8 / 78.6 (optional others) | Retracement of the latest HTF swing |
| **Golden zone** | Shaded band 61.8–78.6 | Primary “interest” area for pullback entries |
| **EMAs** | Fast / slow (+ bias 200 when different) | Timing cloud + hard regime filter |
| **Markers** | Lime ▲ long / red ▼ short | Confluence signals on **closed** bars |
| **Panel** | Top-left `Comment` text | Mode, EMAs, swing, RSI, last signal (Wine-safe) |

**iCustom signal buffer: `8`** (`+1` long, `−1` short, `0` flat).

---

## 2. Install and compile

From the repo (all Wine prefixes you use):

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/18-install-forex-indicator.sh
```

In the MT5 terminal you trade with:

1. **MetaEditor** (F4) → open `Indicators/ForexHtfPivotsFib.mq5`  
2. **Compile** (F7) — 0 errors  
3. Confirm short name / panel shows **v1.42** (or later)

Depends on `Include/ForexUtils.mqh` (copied by the install script).

---

## 3. Attach to a chart

### Chart choice

| Preference | Timeframe | Notes |
|------------|-----------|--------|
| **Recommended** | **H1** or **M15** | Execution chart; 4H + Daily structure on top |
| OK | M5 / M30 | More noise; same HTF logic |
| Avoid as primary | Above H4 | 4H pivot layer disables; Fib falls back to **Daily** |

**Symbols:** majors / minors / gold (`XAUUSD`, `XAUUSD.r`, etc.). Not for BTC (use `BtcTrendPullback`).

**One chart per timeframe (Wine):** do **not** spam the TF toolbar on a chart that carries this indicator. Each flip still unload/reloads the indicator (journal: loaded/removed). v1.42 no longer mass-deletes GDI objects on that path — that was the measured freeze trigger on 2026-08-13 — but OnInit/OnDeinit churn remains. Prefer one tab per TF (e.g. US30 M1 + US30 M15) and switch tabs instead of flipping one chart.

### Steps

1. Open symbol → prefer **chart tab** (do not undock under Wine).  
2. Navigator → **Indicators** → **ForexHtfPivotsFib** → drag onto chart.  
3. Set **Trading mode** (see §4) → OK.  
4. Toolbar: leave **Algo Trading** green only if you also use EAs (logger / bridge).

### Confirm it loaded

Top-left panel should look like:

```text
HTF Fib v1.42
Mode   INTRADAY  (M15-H1 ...)
EMAs   20/50 bias 200
Fib src 4H
Swing  BULL | BEAR | none
Golden ...
RSI    ...
RSI MA ...  (above MA | below MA)
...
Signal +0 | +1 | -1
```

---

## 4. Trading mode (start here)

Input group **`=== Trading mode ===`**

| Input | Meaning |
|-------|---------|
| **`InpTradingMode`** | Preset: **INTRADAY** or **SWING** |
| **`InpManualOverride`** | `false` (default): mode owns EMA + Fib source + 4H visibility. `true`: use the detailed inputs below instead |

### Mode presets

| | **INTRADAY** (default) | **SWING** |
|--|------------------------|-----------|
| **EMAs** | Fast **20** / Slow **50** + bias **200** | Fast **50** / Slow **200** (bias = 200) |
| **Fib source** | **4H** pivots | **Daily** pivots |
| **4H lines** | Shown (if chart ≤ H4) | Hidden (Daily focus) |
| **Chart hint** | M15–H1 | H4–D1 (H1 for entries OK) |

### How to switch modes

1. Right-click chart → **Indicators List** (or Ctrl+I if it works).  
2. Select **ForexHtfPivotsFib** → **Properties**.  
3. **`InpTradingMode`** → `FX_MODE_INTRADAY` or `FX_MODE_SWING`.  
4. Keep **`InpManualOverride = false`** unless you want full manual control.  
5. OK → panel should show `Mode INTRADAY` or `Mode SWING` and the matching EMA numbers.

**Tip:** Prefer mode switch over hand-editing EMA every day (faster, fewer Wine reloads).

---

## 5. How to read the chart

### 5.1 Pivots (structure)

- **Confirmed** pivot high/low: needs `left` bars + `right` bars of confirmation (default **5/5**).  
- Until confirmation, no new pivot line — **non-repainting** by design (can feel “late”).  
- **4H** lines: short-term HTF structure.  
- **Daily** lines: larger map (always available).  
- Labels optional (`InpShow4hLabels` / `InpShowDailyLabels`) — off by default to reduce clutter.

### 5.2 Swing + Fib

1. Indicator walks confirmed pivots on the **Fib source** TF (4H or Daily).  
2. Builds a **directional swing** (bullish low→high or bearish high→low).  
3. Draws Fib **retracements** of that swing:  
   - Bullish: pullback **down** from swing high  
   - Bearish: pullback **up** from swing low  
4. **Golden zone** = band between **61.8%** and **78.6%** (primary interest).

Default Fib levels: **50, 61.8, 78.6** on; 23.6 / 38.2 off.

If panel shows `Golden (need swing)`: not enough alternating confirmed pivots yet — wait or lower `left`/`right` (more sensitive, more noise).

### 5.3 EMAs

| Line | Color (default) | Role |
|------|-----------------|------|
| Fast | Deep sky blue | Timing (20 or 50) |
| Slow | Orange | Short structure (50 or 200) |
| Bias | Gold | Regime filter (**200**); drawn when period ≠ slow (intraday) |

**Regime rule (signals):** long only if close **above** bias EMA; short only if close **below** bias EMA (when bias filter is on via mode).

### 5.4 Markers (signals)

On a **closed** bar, a marker can fire when **all** of the following hold:

**Long**

1. Swing is **bullish** and price is in the **golden zone** (between 61.8 and 78.6).  
2. Close **> EMA bias (200)**.  
3. RSI ≤ **`InpRsiLongMax`** (default **35**).  
4. If **`InpUseRsiMaFilter`**: RSI **above** its MA (turning up while still “soft”).  
5. Optional: **`InpRequireCandle`** bullish confirmation.  
6. Edge-style: not already true on the previous closed bar (reduces spam).

**Short** — mirror (bearish swing, golden zone, close &lt; bias, RSI ≥ 65, RSI below MA if filter on).

**Visual/manual first.** Markers are confluence aids, not auto-trade permission.

---

## 6. Input reference

### Trading mode

| Input | Default | Notes |
|-------|---------|--------|
| `InpTradingMode` | INTRADAY | Preset |
| `InpManualOverride` | false | true = ignore mode for Fib source / 4H show / EMAs |

### EMAs (only if manual override)

| Input | Default | Notes |
|-------|---------|--------|
| `InpEmaFast` | 20 | Manual fast |
| `InpEmaSlow` | 50 | Manual slow |
| `InpEmaBias` | 200 | Manual regime |
| `InpShowEmas` | true | Plot fast/slow |
| `InpShowBiasEma` | true | Plot bias when useful |

### HTF pivots

| Input | Default | Notes |
|-------|---------|--------|
| `InpLeft4h` / `InpRight4h` | 5 / 5 | Higher = fewer, later pivots |
| `InpLeftDaily` / `InpRightDaily` | 5 / 5 | Same for Daily |
| `InpShow4hLines` | true | Still gated by mode when not manual |
| `InpShowDailyLines` | true | |
| Colors / labels | — | Optional |

### Fibonacci

| Input | Default | Notes |
|-------|---------|--------|
| `InpFibSource` | H4 | Used when **manual** override; else mode picks H4/Daily |
| `InpShowFib*` | 50/618/786 on | Toggle levels |
| `InpShowGoldenZone` | true | Shade 61.8–78.6 |
| Colors | — | Wine: keep high contrast |

### RSI + RSI-MA

| Input | Default | Notes |
|-------|---------|--------|
| `InpShowMarkers` | true | Arrows |
| `InpRsiPeriod` | 14 | |
| `InpRsiMaPeriod` | 14 | Signal line on RSI |
| `InpRsiMaMethod` | SMA | SMA or EMA |
| `InpRsiLongMax` | 35 | Long zone ceiling |
| `InpRsiShortMin` | 65 | Short zone floor |
| `InpUseRsiMaFilter` | true | RSI vs RSI-MA alignment |
| `InpRequireCandle` | false | Extra candle filter |

### Display

| Input | Default | Notes |
|-------|---------|--------|
| `InpShowPanel` | true | `Comment()` panel |
| `InpArrowOffsetPips` | 4 | Arrow distance from high/low |

---

## 7. Recommended workflows

### A. Intraday pullback (default)

1. Chart **H1** (or M15).  
2. Mode **INTRADAY**.  
3. Wait for **bullish/bearish swing** + **golden zone** drawn.  
4. Prefer **London / NY** sessions (use broker server clock; session filter is **not** built into this indicator’s mode the same way as the Template — use your own session discipline or Template on a second chart if needed).  
5. Long: price in GZ, above EMA200, RSI soft but above RSI-MA → marker or discretionary entry.  
6. Risk: outside structure / beyond 78.6 invalidation or ATR-based stop (manual).

### B. Swing

1. Chart **H4** or **D1** (or H1 for timing with Daily Fib).  
2. Mode **SWING**.  
3. Fib from **Daily** pivots; fewer trades, larger structure.  
4. EMA 50/200 alignment as regime.

### C. Journal only (no visual need)

- Attach **ForexSignalLogger** with  
  - `InpIndicatorName = ForexHtfPivotsFib`  
  - `InpSignalBuffer = 8`  
  - `InpMaxSpreadPips` as you like (e.g. 2.5 FX, 0 for very wide symbols)  
- Logger loads a **hidden** HTF Fib via `iCustom` (defaults). For exact parity with on-chart inputs, keep chart Fib on **mode defaults** or accept possible mismatch until inputs are mirrored in the logger.

### D. With ForexIndicatorTemplate

**Best:** HTF Fib **alone** on the trade chart.  

**Both on one chart:** Template with **dashboard off + arrows off**; HTF Fib owns panel and markers. See conversation notes / roadmap. Prefer not two arrow systems.

### E. With Mt5ArchBridge

- Bridge is a **separate EA**.  
- **One chart only** (any symbol).  
- Not the same as HTF Fib.

---

## 8. iCustom buffers (EAs / logger)

| Index | Content |
|------:|---------|
| 0 | EMA fast |
| 1 | EMA slow |
| 2 | EMA bias |
| 3 | Long arrow price (or empty) |
| 4 | Short arrow price (or empty) |
| 5 | Fib 61.8 |
| 6 | Fib 78.6 |
| 7 | Swing direction (+1 / −1) |
| **8** | **Signal (+1 / −1 / 0)** |
| 9 | RSI |
| 10 | RSI-MA |

```mql5
double sig[];
ArraySetAsSeries(sig, true);
// last closed bar
if(CopyBuffer(handle, 8, 1, 1, sig) > 0)
  {
   if(sig[0] > 0) { /* long */ }
   if(sig[0] < 0) { /* short */ }
  }
```

---

## 9. Broker / Wine notes (this machine)

| Topic | Advice |
|-------|--------|
| Prefixes | `~/.mt5-wsf`, `~/.mt5-vantage`, `~/.mt5-fpmarkets` — install script deploys to all found |
| Charts | Tabs only; undocked chart windows often black |
| Panel | Uses `Comment()` (Wine-safe); not multi-color labels |
| Mouse | Prefer **primary** monitor; no Wine virtual desktop |
| EMA tweaks | Changing inputs reloads indicator; avoid spam-editing on huge histories |
| TF flipping | Prefer one chart per TF (see §3); v1.42 skips ObjectsDeleteAll on chartchange |
| Sessions | Fib indicator does **not** hard-block Asian like Template; manage sessions yourself in INTRADAY |

Switch broker:

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/16-use-broker.sh vantage   # or fpmarkets, wsf
./scripts/04-start-terminal.sh --detach
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| No indicator in Navigator | `./scripts/18-install-forex-indicator.sh` → F7; right-click Indicators → Refresh |
| Panel missing / wrong | Re-attach; ensure `InpShowPanel=true`; only one indicator writing `Comment` |
| EMA numbers don’t change | Set **`InpManualOverride=true`**, or switch **Mode** (mode owns EMAs when override false) |
| No Fib / “need swing” | Wait for confirmed pivots; or lower left/right; check chart ≤ H4 for 4H source |
| No arrows | Closed bar only; check bias side, golden zone, RSI + RSI-MA filters |
| Freezes on param / TF change | Panel must show **v1.42+**; one chart per TF; fewer charts; one bridge EA only. Watchdog: `mt5-freeze-watch.timer` |
| Logger ≠ chart signals | Logger `iCustom` uses **default** inputs unless extended; align mode defaults |
| Gold symbol | Use your broker’s name (`XAUUSD` vs `XAUUSD.r`) |

---

## 11. What this is *not*

- Not a multi-broker account switcher  
- Not session-momentum / z-score (that lives in cTrader Python)  
- Not BTC trend pullback (use **BtcTrendPullback**)  
- Not a substitute for news, spread, sizing, or prop-firm rules  

Treat markers as **observe / journal** until you have a written edge and risk plan.

---

## 12. Quick start checklist

- [ ] Install script run  
- [ ] F7 compile succeeds  
- [ ] Chart H1 (or M15), majors/gold  
- [ ] Mode set (INTRADAY or SWING)  
- [ ] Panel shows version + EMAs + Fib src  
- [ ] Golden zone appears after swings form  
- [ ] Optional: SignalLogger buffer **8**  
- [ ] Optional: Mt5ArchBridge on **one** chart only  
- [ ] Save chart **Template** once happy  

---

## 13. Backtesting (MT5 Strategy Tester + offline)

### 13.1 Expert Advisor: `ForexHtfFibTester`

| Item | Value |
|------|--------|
| File | `mql5/Experts/ForexHtfFibTester.mq5` |
| Signal | `iCustom` → **ForexHtfPivotsFib** buffer **8** |
| Risk | Fixed lots (default 0.10) or risk % |
| Exits | SL = 1.5×ATR(14), TP = 2.0×ATR(14) |
| Rules | New bar only; reverse on opposite signal; max spread filter |

**Compile:** MetaEditor → `Experts/ForexHtfFibTester.mq5` → F7 (indicator must already be compiled).

### 13.2 GUI Strategy Tester (recommended under Wine)

1. Open MT5 (any broker prefix with data for the symbol).  
2. **View → Strategy Tester** (Ctrl+R if bound).  
3. **Expert:** `ForexHtfFibTester`  
4. **Symbol:** e.g. `EURUSD` · **Period:** H1  
5. **Dates:** e.g. 2024.06.01 – 2025.01.01  
6. **Model:** 1 minute OHLC (or every tick based on real ticks if available)  
7. **Deposit:** 10000 · **Visual mode:** optional  
8. **Start**

Ensure history is downloaded (open EURUSD H1 chart and scroll left first).

Headless Single tester (Wine): use `scripts/19-run-htf-fib-backtest.sh` (Login from `common.ini`, ASCII config, EA v1.40 `.set`). Example: `WINEPREFIX=~/.mt5-vantage KILL_EXISTING=1 ./scripts/19-run-htf-fib-backtest.sh XAUUSD H1 2024.01.01 2025.01.01`. GUI Strategy Tester remains fine if preferred.

Helper script (compile + config template):

```bash
export WINEPREFIX=~/.mt5-vantage   # or fpmarkets / wsf
cd ~/Projects/trading/mt5-arch-integration
./scripts/19-run-htf-fib-backtest.sh EURUSD H1 2024.06.01 2025.01.01
```

### 13.3 Offline research script (Dukascopy CSV)

Approximation of the same rules on H1 CSV (H4 pivots resampled from H1). **Not identical** to MT5 `iCustom`.

```bash
# needs pandas/numpy
python3 scripts/htf_fib_offline_backtest.py \
  --csv ~/Projects/trading/ctrader-trading-agent/data/dukascopy/eurusd_h1_2022-01-01_2026-03-01.csv \
  --from 2022-01-01 --to 2024-12-31 \
  --no-rsi-ma-filter \
  --out results/htf_fib_offline.json
```

| Setting | Typical effect |
|---------|----------------|
| RSI-MA filter **on** (indicator default) | Very few trades |
| `--no-rsi-ma-filter` | More trades; still not a verified edge |

Example offline run (EURUSD H1, 2022–2024, filter off, 0.1 lot, ATR exits):

- Trades: 22 · Win rate ≈ 32% · Net ≈ −$96 · PF ≈ 0.57  
- Treat as **research smoke**, not production readiness.

### 13.4 Interpreting results

- Sparse signals with RSI-MA filter is expected (strict confluence).  
- Tune SL/TP, mode, and filters in the **EA inputs**, re-run tester.  
- Optimize only out-of-sample after a fixed rule set (walk-forward).  

---

## Related docs

| Doc | Content |
|-----|---------|
| [FOREX-MT5-ROADMAP.md](FOREX-MT5-ROADMAP.md) | Observe → paper → live waves |
| [CHARTS-AND-STABILITY.md](CHARTS-AND-STABILITY.md) | Wine / Hyprland charts, mouse, clipboard |
| [../mql5/README.md](../mql5/README.md) | All MQL5 sources + buffer tables |
| TradingView source | `manual-trading-agent/tradingview/tradingview_pivot_rsi_ema.pine` |

---

*Last aligned with ForexHtfPivotsFib v1.31 and ForexUtils trading-mode helpers.*
