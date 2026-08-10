# BtcTrendPullback — Design Memo (BTC-only MT5 Indicator)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-04 |
| **Status** | Design draft |
| **Indicator name** | `BtcTrendPullback` |
| **Repo boundary** | Platform only (`mt5-arch-integration`): visual + `iCustom` + logger — **no** `OrderSend` |
| **Primary chart** | `BTCUSD` H1 (HTF bias: H4 completed bars) |
| **Logger contract** | `ForexSignalLogger` · `InpSignalBuffer=7` · `InpSignalShift=1` |

---

## 1. Purpose of this document

This memo freezes the **implementation design** for a BTC-only chart indicator on Wine MT5. It is the durable handoff between:

1. Research lessons from `crypto-agent` (what chart grammar works; what failed),
2. Market realities of retail **BTCUSD CFDs** (no true volume, gaps, ATR-based risk),
3. Platform patterns already proven in `ForexHtfPivotsFib` + `ForexSignalLogger` (buffers, non-repaint, closed-bar signal).

**Audience:** implementers of `mql5/Indicators/BtcTrendPullback.mq5` and Wave B observe operators.  
**Not an EA design** — trading, sizing, and risk remain outside this repo (see AGENTS.md).

---

## 2. Executive summary

### What to build

**`BtcTrendPullback`**: a visual-first chart indicator for **BTCUSD CFDs** that implements investable chart grammar for Wave B observe:

| Layer | Role |
|-------|------|
| **H4 completed-bar bias** | EMA50 > EMA200 stack + separation strength → buffer 6 (`+1` / `−1` / `0`) |
| **H1 closed-bar entries** | Shallow pullback to EMA50 with **stateful recovery** (RSI reclaim & rising, MACD hist recovering & rising, rising close); optional non-extended continuation above EMA50 |
| **Liveliness** | ATR% floor — block dead calm / no-range bars |
| **Stop guides** | Mid ± *k*×ATR14 price bands (buffers 2–3) — not FX pips |
| **Signal** | Ternary buffer 7 (`+1` long / `−1` short / `0` flat), edge-triggered, closed bars only — same `iCustom` contract as the FX pack |
| **Long-primary** | Shorts only under HTF downtrend stack (mirrored), never RSI-overbought alone |

**Platform-only:** markers + `iCustom` ternary signal + optional panel. Wire `ForexSignalLogger` for a journal. **Never** `OrderSend`.

### What NOT to port from FX Fib (`ForexHtfPivotsFib`)

`ForexHtfPivotsFib` is a confirmed HTF **pivot + directional Fib golden-zone (61.8–78.6)** tool tuned for FX/gold swing geometry and **pip UI**. BTCUSD CFDs need **continuous trend-stack + mean-reversion-to-EMA** grammar (crypto-agent TrendPullback), not rare swing-Fib confluence:

| Keep (Wine-safe contract) | Do **not** port |
|---------------------------|-----------------|
| 8-buffer layout, signal index **7**, ternary ints | Fib swing machine / golden-zone mandatory logic |
| `PLOT_EMPTY_VALUE`, series-false plot arrays | `FxPipSize` / `FxPipsToPrice` / `InpArrowOffsetPips` |
| Closed-bar non-repaint; skip forming bar | `ENUM_FX_SESSION` / Asian–London–NY as BTC liquidity |
| `iMA`/`iRSI` handles + `IndicatorRelease` | `FxSpreadPips` / logger pip spread as absolute BTC gate |
| ChartID-prefixed objects + panel pattern | Pip-centric panel (`%.5f`) and FX lot/pip math |
| Log-only EA path (`ForexSignalLogger`) | Assuming pivot legs survive weekend/maintenance gaps cleanly |

**Why:** weekend/maintenance gaps break clean pivot legs; `tick_volume` is not depth; stops are ATR×price not pips; research abandoned ultra-selective structure/MTF routers that starve trade count.

---

## 3. Lessons from crypto-agent

### 3.1 Summary thesis (what actually works)

Investable visual/structural language for BTC is **not** a rare 4h-only multi-AND router. It is clear **chart grammar**:

1. **EMA50 / EMA200** trend stack and strength  
2. **Shallow pullback** near EMA50 (VWAP optional; OFF by default on MT5 CFDs)  
3. **ATR%** as liveliness gate  
4. **Stateful recovery** — rising RSI reclaim, rising MACD histogram, rising close  
5. Optional **continuation** when price is above EMA50 but not extended  

**MTF shape is sound architecture** (higher-TF regime context + lower-TF entry). **OHLCV-only multi-AND regime classifiers** and **ultra-selective BTC/4h entries** failed as investable systems (too few trades, calm-bull blindness, short bias).

### 3.2 Keep (structural language to encode)

| Pattern | Detail |
|---------|--------|
| Uptrend structure | `close > ema_200` AND `ema_50 > ema_200` with `trend_strength_pct = (ema_50 − ema_200) / ema_200` |
| Pullback band | Shallow `%` distance from EMA50 (and optional VWAP) — not deep dumps |
| Recovery markers | Bar-to-bar: RSI reclaiming a level **and** rising; MACD hist recovering **and** rising; close recovering |
| Continuation | Strong trend + `close ≥ ema_50` + not extended vs EMA50 (+ optional VWAP) + RSI/MACD momentum |
| Deep-reclaim arm/fire | Arm under EMA50 (windowed N bars); fire on reclaim with momentum (optional, default off) |
| ATR% floor | Dead markets / no range → no signal |
| Panic-block veto | Asymmetric risk-off: RSI very low **or** ATR% very high, especially `close < ema_200` |
| MTF layering | Higher TF (H4) context on lower TF (H1) entry via **as-of completed bars only** |
| Promotion discipline | Research → backtest → paper → live; **min trade-count gates** before treating rare edges as real |

Indicators used in the successful grammar (subset for MT5 v1):  
`close`, `ema_50`, `ema_200`, `rsi_14`, `atr_14` / `atr_pct`, `macd_hist`, optional `vwap`.  
(Python-only features like `trend_consistency`, `volatility_percentile`, BB squeeze can stay visual-future — not multi-AND gates in v1.)

### 3.3 Avoid

- **Triple-AND OHLCV regime** (`abs(ema_slope)` AND `trend_consistency > 60` AND `volatility_percentile > 50`) — blocks calm BTC bulls  
- **BTC/4h ultra-restrictive pullbacks** (~3 trades / 8 months — profitable but not investable)  
- Assuming OHLCV-only regime features alone produce durable BTC directional edge (2024 MTF family closed as failed)  
- **Short bias** from RSI > overbought as primary while longs need deep RSI oversold  
- Chasing extended price far above EMA50/VWAP without extension caps  
- Treating **threshold retunes** as a fix when sample size is the real blocker  
- **Lookahead** on higher TF — always completed higher-TF bars only  
- **Porting full Python strategy engines** to MT5; port structural layers (lines, zones, reclaim flags) only  

### 3.4 Failed theses (do not re-open without new data)

| Thesis | Outcome |
|--------|---------|
| BTC/4h RegimeRouter | Paper-profitable but ~3 trades/8 months — not investable |
| MTF Pullback (4h trend + 1h pullback) | Failed 2024 (−$2.5k, ~98% shorts) |
| MTF Continuation (4h trend + 1h reclaim) | Failed 2024 (−$3.7k) |
| MTF Breakout/Expansion (4h vol + 1h reclaim) | Failed 2024 (−$4.4k) |
| OHLCV multi-condition regime classifier | Misses steady low-vol BTC uptrends |
| Short-heavy RSI-overbought primary | Dominates when longs require RSI oversold |
| Threshold sweeps | Slight metric noise; does not rescue losing BTC MTF family |

### 3.5 Timeframe shapes (context)

| Shape | Use |
|-------|-----|
| **4h regime + 1h entry** | **Primary for this indicator** |
| 15m entry + 1h regime | Day-trading alternative (not v1 default) |
| 4h entry + 1d regime | Position alternative |
| 1h entry + 1d regime | Multi-day swings |
| Single-TF trend-pullback | EMA/VWAP/RSI/MACD/ATR% on entry bar only |

---

## 4. MT5 constraints (Wine, logger, platform boundary)

### 4.1 Platform boundary (AGENTS.md)

- **This repo:** Wine MT5 + RPyC/mt5linux + thin Python CLI + MQL5 visuals/logger  
- **Not here:** strategy engines, risk managers, Telegram bots, TimescaleDB, agent orchestration  
- Secrets only via `.env`; never log `MT5_PASSWORD`  
- No live smoke orders without explicit live flag + user consent  
- Prefer observe / journal first (FOREX roadmap Waves B→D before any live path)

### 4.2 BTC market / CFD constraints

| Constraint | Implication for indicator |
|------------|---------------------------|
| Broker symbol **BTCUSD** (FP/Vantage; aliases possible) | Resolve live `SymbolInfo`; never hardcode sole name for trading paths |
| Cash CFD, not spot | Maintenance/weekend gaps; stops may not fill while offline |
| `tick_volume` = broker tick count | Not exchange depth; VWAP is soft/optional and **OFF by default** |
| No FX pip model | Offsets/bands in **price or ATR×frac**; not `FxPipsToPrice` |
| No FX session model | Do not use Asian/London/NY gates as BTC liquidity |
| Contract specs differ by broker | Digits, tick size, margin — read live before any trading path (agent owns sizing) |
| Bridge lag (file/RPyC, seconds) | Decisions on **closed H1/H4 bars** only so lag ≪ bar duration |
| One Wine prefix per broker brand | Re-verify symbols after `16-use-broker.sh` switch |

### 4.3 Patterns to reuse from ForexHtfPivotsFib

- `iCustom` signal buffer: **+1 / −1 / 0**, index **7**  
- `CopyBuffer(handle, 7, 1, 1, sig)` on last closed bar; `ArraySetAsSeries(sig, true)` in EA  
- `OnCalculate`: skip forming bar (`i == rates_total - 1`) for signal/arrows  
- Buffers as **series-false** (index 0 = oldest); `PLOT_EMPTY_VALUE` for plots  
- `INDICATOR_CALCULATIONS` for non-plot signal/state buffers  
- Built-in handles + `IndicatorRelease` on deinit; ChartID-prefixed objects  
- Log-only EA: `iCustom` → Print/CSV; never trade classes  
- New-bar gate + dedupe by signal bar time in logger  
- Install via `./scripts/18-install-forex-indicator.sh` + MetaEditor **F7**  
- Optional edge-trigger to avoid spam markers every bar in zone  

### 4.4 Do not reuse from FX utils for BTC risk/UI

- `ENUM_FX_SESSION` / `FxDetectSession`  
- `FxPipSize` / `FxPipsToPrice` / `InpArrowOffsetPips` (and XAU special-cases as BTC template)  
- `FxSpreadPips` and logger `InpMaxSpreadPips=2.5` as absolute BTC spread gate  
- 100_000 contract / $10-per-pip lot math  
- Hardcoded major-FX chart recipes and pip-centric panel formats  
- Treating London+NY overlap defaults as crypto peak liquidity  

### 4.5 Buffer contract lessons (reference)

Primary FX pattern (`ForexHtfPivotsFib`): 8 buffers — EMA50, EMA200, Long/Short arrows, fib618, fib786, swingDir, **signal@7**.  
`BtcTrendPullback` reuses the **same signal index and logger wiring**, but replaces Fib/swing buffers with **ATR stop-guides** and **HTF bias**.

---

## 5. Indicator specification

### 5.1 Identity

| Field | Value |
|-------|--------|
| **Name / shortname** | `BtcTrendPullback` |
| **File** | `mql5/Indicators/BtcTrendPullback.mq5` |
| **Window** | `#property indicator_chart_window` |
| **Thesis** | See below |
| **Chart TF (default)** | **H1** |
| **HTF (default)** | **H4** (`InpHtfPeriod`, alt `PERIOD_D1`) |
| **Logger compatible** | **Yes** (`InpSignalBuffer=7`, `InpSignalShift=1`) |

### 5.2 Thesis (one paragraph)

Visual-first chart grammar for BTCUSD CFDs (Wave B observe): **H4 completed-bar** EMA50>EMA200 stack + strength as bias; **H1 closed-bar** shallow pullback to EMA50 with stateful recovery (RSI reclaim & rising, MACD hist recovering & rising, rising close); optional non-extended continuation above EMA50; ATR% liveliness floor; ATR×*k* price stop-guide bands. Long-primary (mirror shorts only under HTF downtrend stack). Intentionally avoids crypto-agent rarity traps — no multi-AND OHLCV regime router, no ultra-selective 4h-only entries, no RSI-overbought short bias. VWAP optional and OFF by default (`tick_volume` is not exchange volume). Platform-only: markers + `iCustom` ternary signal; never `OrderSend`.

### 5.3 Plots (visible)

| Plot | Description | Color (suggested) |
|------|-------------|-------------------|
| 1 | EMA50 (chart TF) | Sky blue (`clrDeepSkyBlue`) |
| 2 | EMA200 (chart TF) | Gold (`clrGold`) |
| 3 | ATR lower stop-guide (`mid − k×ATR14`) | Subtle gray/dashed |
| 4 | ATR upper stop-guide (`mid + k×ATR14`) | Subtle gray/dashed |
| 5 | Long arrow (closed-bar pullback reclaim or continuation) | Lime |
| 6 | Short arrow (optional HTF downtrend mirror only) | Orange red |

`#property indicator_plots 6` with `#property indicator_buffers 8`.

### 5.4 Buffer table

| Index | Name | Type | Values / notes |
|------:|------|------|----------------|
| 0 | EMA50 | `INDICATOR_DATA` | Chart-TF EMA fast |
| 1 | EMA200 | `INDICATOR_DATA` | Chart-TF EMA slow |
| 2 | ATR lower stop-guide | `INDICATOR_DATA` | `mid − InpAtrBandMult × ATR14` every bar (visual) |
| 3 | ATR upper stop-guide | `INDICATOR_DATA` | `mid + InpAtrBandMult × ATR14` every bar (visual) |
| 4 | Long arrow | `INDICATOR_DATA` | Price at `low − offset`; **`EMPTY_VALUE` when none** |
| 5 | Short arrow | `INDICATOR_DATA` | Price at `high + offset`; **`EMPTY_VALUE` when none** |
| 6 | HTF_bias | `INDICATOR_CALCULATIONS` | `+1` bull / `−1` bear / `0` chop |
| **7** | **signal** | `INDICATOR_CALCULATIONS` | **`+1` long / `−1` short / `0` flat** — logger target |

**Document in shortname/description:** `Signal buffer 7 (+1/−1/0). Closed bars only.`

**Array convention:** series-false (index 0 = oldest), matching `ForexHtfPivotsFib`.  
**Arrow offset:** `InpArrowOffsetAtrFrac × ATR` in **price** — never pips.  
**Mid for ATR bands:** `InpAtrBandMid` = EMA50 (default) or CLOSE.

---

## 6. Entry / filter logic

### 6.1 Filters (always on or optional as noted)

| # | Filter | Role |
|---|--------|------|
| 1 | **ATR% liveliness floor** | Block dead calm / no-range bars (`atr_pct ≥ InpMinAtrPct`) |
| 2 | **HTF completed-bar only** | No lookahead on forming H4 (`shift ≥ 1`) |
| 3 | **Chart closed-bar only** | Non-repaint markers/signal (`i < rates_total - 1`) |
| 4 | **Extension cap vs EMA50** | No chase far above mean (`≤ InpMaxEma50ExtensionPct` for continuation) |
| 5 | **Optional panic-block** | Veto longs if RSI very low **or** ATR% very high, especially `close < ema200` |
| 6 | **No multi-AND OHLCV regime rarity** | No `trend_consistency AND vol_percentile` stacks |
| 7 | **VWAP gate OFF by default** | Soft band only if `InpUseVwap` |
| 8 | **Optional max spread** | Price or ATR fraction (not FX pips) — logger note: set `InpMaxSpreadPips=0` for BTC |
| 9 | **Edge-trigger** | Prefer setup true now && false on prev closed bar |
| 10 | **Shorts** | Gated by HTF downtrend stack only (no RSI-overbought primary) |

### 6.2 Pseudocode

```
// OnCalculate — after CopyBuffer for all handles

for each bar i from start to rates_total-1:
  // Always paint EMAs and ATR bands when data available
  BufEma50[i], BufEma200[i] ← chart MA series
  atr14 ← chart ATR
  mid ← (InpAtrBandMid == EMA50) ? ema50 : close
  if InpShowAtrBands:
    BufAtrLower[i] ← mid - InpAtrBandMult * atr14
    BufAtrUpper[i] ← mid + InpAtrBandMult * atr14

  // --- HTF bias: last fully completed H4 only (never forming H4) ---
  h4_close, h4_ema50, h4_ema200 ← iMA/iClose on InpHtfPeriod, shift ≥ 1
  trend_strength_pct ← (h4_ema50 - h4_ema200) / h4_ema200
  if h4_close > h4_ema200 AND h4_ema50 > h4_ema200
     AND trend_strength_pct ≥ InpMinTrendStrengthPct:
       HTF_bias ← +1
  else if h4_close < h4_ema200 AND h4_ema50 < h4_ema200
     AND -trend_strength_pct ≥ InpMinTrendStrengthPct:  // inverse strength
       HTF_bias ← -1
  else:
       HTF_bias ← 0
  BufHtfBias[i] ← HTF_bias

  // --- Signal / arrows: closed bars only ---
  if i == rates_total - 1:
    BufSignal[i] ← 0
    BufLong[i] ← EMPTY_VALUE
    BufShort[i] ← EMPTY_VALUE
    continue

  atr_pct ← atr14 / close
  signal ← 0

  // Liveliness
  if atr_pct < InpMinAtrPct:
    write_flat(i); continue

  // --- LONG primary (HTF_bias == +1) ---
  if HTF_bias == +1:
    if InpPanicBlock and panic_long_veto(rsi, atr_pct, close, ema200):
      // force flat for long
      pass
    else:
      near_ema50 ← abs(close - ema50) / ema50 ≤ InpMaxPullbackPct
      near_vwap  ← (not InpUseVwap) OR abs(close - vwap)/vwap ≤ InpVwapPullbackPct

      recovery_ok ←
          (rsi ≥ InpRsiReclaim AND rsi > rsi[prev])
          AND (macd_hist ≥ InpMinMacdHist AND macd_hist > macd_hist[prev])
          AND (close > close[prev])

      // (A) Pullback reclaim
      setup_pullback ← near_ema50 AND near_vwap AND recovery_ok

      // (B) Continuation (optional)
      strong_trend ← trend_strength_pct ≥ InpStrongTrendStrengthPct  // from HTF
      ext_pct ← (close - ema50) / ema50
      setup_cont ← InpAllowContinuation
          AND strong_trend
          AND close ≥ ema50
          AND 0 ≤ ext_pct ≤ InpMaxEma50ExtensionPct
          AND rsi ≥ InpContinuationRsi
          AND (rsi rising OR macd_hist rising)

      // (C) Deep-reclaim optional state machine (bar counters, not tick state)
      setup_deep ← false
      if InpDeepReclaimEnabled:
        // arm: under ema50 within arm distance for N closed bars
        // fire: reclaim ema50 + rising RSI/MACD + not extended
        setup_deep ← deep_reclaim_fire(i)

      long_setup ← setup_pullback OR setup_cont OR setup_deep

      if InpEdgeTrigger:
        long_fire ← long_setup AND NOT long_setup_on_prev_closed_bar
      else:
        long_fire ← long_setup

      if long_fire:
        signal ← +1
        if InpShowMarkers:
          BufLong[i] ← low[i] - InpArrowOffsetAtrFrac * atr14

  // --- SHORT: only if InpAllowShorts and HTF_bias == -1 (mirrored) ---
  if InpAllowShorts AND HTF_bias == -1 AND signal == 0:
    // mirror of long: near ema50 from above, recovery down (RSI falling through
    // reclaim-from-above, macd_hist falling, close < close[prev]), optional
    // continuation below ema50 with extension cap, never RSI>overbought alone
    short_setup ← mirrored_short_conditions(...)
    if InpEdgeTrigger:
      short_fire ← short_setup AND NOT short_setup_prev
    else:
      short_fire ← short_setup
    if short_fire:
      signal ← -1
      if InpShowMarkers:
        BufShort[i] ← high[i] + InpArrowOffsetAtrFrac * atr14

  BufSignal[i] ← signal   // ternary int only: +1 / -1 / 0
  if signal != +1: BufLong[i]  ← EMPTY_VALUE (unless already set)
  if signal != -1: BufShort[i] ← EMPTY_VALUE
```

**Invariants:**

- Write `BufSignal` only on **closed** bars.  
- Plots use `EMPTY_VALUE` when inactive.  
- Signal values are **ternary integers** only (consumers `MathRound` to int).  
- HTF features never use the **forming** H4 bar.  
- Edge-trigger preferred so markers/signals do not spam every bar while price sits in the pullback zone.

### 6.3 Panic-block (long veto sketch)

```
panic_long_veto ← InpPanicBlock AND (
     rsi ≤ InpPanicRsi
  OR atr_pct ≥ InpPanicAtrPct
) AND (close < ema200)   // especially under slow MA; exact combo tunable
```

Default: `InpPanicRsi=35`, `InpPanicAtrPct=0.08`.

---

## 7. Inputs (defaults)

Group names are suggested for MetaTrader Inputs UI.

```
=== EMAs (chart TF) ===
InpEmaFast                 = 50
InpEmaSlow                 = 200

=== HTF bias ===
InpHtfPeriod               = PERIOD_H4          // alt: PERIOD_D1
InpMinTrendStrengthPct     = 0.01               // 1.0%
InpStrongTrendStrengthPct  = 0.015              // 1.5%

=== RSI ===
InpRsiPeriod               = 14
InpRsiReclaim              = 50
InpContinuationRsi         = 54

=== MACD ===
InpMacdFast                = 12
InpMacdSlow                = 26
InpMacdSignal              = 9
InpMinMacdHist             = 0

=== ATR / liveliness / bands ===
InpAtrPeriod               = 14
InpMinAtrPct               = 0.01               // 1.0% of price
InpAtrBandMult             = 2.0
InpAtrBandMid              = EMA50              // or CLOSE

=== Pullback / extension ===
InpMaxPullbackPct          = 0.015              // 1.5%
InpMaxEma50ExtensionPct    = 0.03               // 3%

=== VWAP (optional; OFF by default) ===
InpUseVwap                 = false
InpVwapPullbackPct         = 0.01
InpVwapAnchor              = session_or_rolling_N   // tick_volume weighted if enabled

=== Modes ===
InpAllowContinuation       = true
InpDeepReclaimEnabled      = false
InpDeepReclaimArmBars      = 3
InpAllowShorts             = true
InpPanicBlock              = true
InpPanicRsi                = 35
InpPanicAtrPct             = 0.08
InpEdgeTrigger             = true

=== Display ===
InpShowMarkers             = true
InpShowAtrBands            = true
InpShowPanel               = true
InpArrowOffsetAtrFrac      = 0.15               // price offset = frac × ATR; never pips
```

**Panel fields (if `InpShowPanel`):** HTF bias, `atr_pct`, `trend_strength_pct`, last signal, VWAP on/off; format with `_Digits`; **no pip labels**.

---

## 8. Logger / `iCustom` contract

### 8.1 Indicator side

| Contract item | Value |
|---------------|--------|
| Compiled name | `BtcTrendPullback` (no `.ex5` in logger input) |
| Signal buffer index | **7** |
| Signal shift for EA | **1** (last **closed** bar) |
| Values | `+1` long, `−1` short, `0` flat |
| Forming bar | Always write `0` / no arrows |

### 8.2 ForexSignalLogger wiring

```
InpIndicatorName   = "BtcTrendPullback"
InpSignalBuffer    = 7
InpSignalShift     = 1
InpMaxSpreadPips   = 0          // FX-oriented; disable for BTC
```

**Note:** `InpMaxSpreadPips` is FX-oriented. For BTC, set **0** (off) or document a later price/ATR-fraction alternative. Do not treat 2.5 pips as a BTC gate.

### 8.3 EA consumer snippet

```mql5
double sig[];
ArraySetAsSeries(sig, true);
// handle = iCustom(_Symbol, PERIOD_H1, "BtcTrendPullback", ...inputs...);
if(CopyBuffer(handle, 7, 1, 1, sig) == 1)
  {
   int s = (int)MathRound(sig[0]);
   if(s == 1)  { /* long */ }
   if(s == -1) { /* short */ }
   // ignore 0
  }
```

### 8.4 CSV / journal path

Same logger infrastructure as Wave B FX:

```
MQL5/Files/forex_signals/<SYMBOL>_<TF>.csv
```

Wine example (Vantage):  
`~/.mt5-vantage/drive_c/Program Files/Vantage International MT5/MQL5/Files/forex_signals/`  
Expect `BTCUSD_H1.csv` when attached to BTCUSD H1.

Dedupe by signal bar time remains the logger’s responsibility (new-bar gate).

---

## 9. Implementation order (files under `mql5/`)

Execute in order; each step should leave a compilable intermediate where practical.

1. **Scaffold** `Indicators/BtcTrendPullback.mq5`  
   - `#property indicator_chart_window`, 8 buffers / 6 plots  
   - SHORTNAME / description documents signal buffer **7**  
   - Mirror `ForexHtfPivotsFib` `OnInit` buffer layout + `PLOT_EMPTY_VALUE` + series-false arrays  

2. **Handles**  
   - Chart: `iMA` EMA50/200, `iRSI`, `iMACD`, `iATR`  
   - HTF: separate `iMA` (and optional `iATR`) on `InpHtfPeriod`  
   - `IndicatorRelease` all on deinit  
   - ChartID-prefixed objects for optional panel  

3. **`OnCalculate` skeleton**  
   - `CopyBuffer` all series  
   - Compute `atr_pct`, `trend_strength`, distances  
   - Skip `i == rates_total - 1` for signal/arrows  
   - Mid ± *k*×ATR into buffers 2–3 every bar for visual guide  

4. **HTF bias**  
   - Completed H4 only (`shift ≥ 1`)  
   - Write buffer 6  
   - No forming-bar HTF features  

5. **Long entry functions**  
   - Pullback recovery  
   - Optional continuation  
   - Optional deep-reclaim **state machine with bar counters** (not tick state)  
   - Apply ATR% + panic-block + extension caps  

6. **Optional short mirror** under `HTF_bias == -1`  
   - Default VWAP path **stubbed/OFF** (tick_volume-weighted session/rolling VWAP only if `InpUseVwap`)  

7. **`BufSignal` ternary + edge-trigger**  
   - Arrows at `low − offset` / `high + offset` with ATR-fraction offset (**not** `FxPipsToPrice`)  
   - Never write live-bar signals  

8. **Panel**  
   - HTF bias, `atr_pct`, `trend_strength_pct`, last signal, VWAP on/off  
   - `digits = _Digits`; no pip labels  

9. **Wire ForexSignalLogger**  
   - `InpIndicatorName=BtcTrendPullback`, buffer 7, shift 1  
   - Document BTC spread input caveat  

10. **Install / compile**  
    - Extend `scripts/18-install-forex-indicator.sh` copy list to include `BtcTrendPullback.mq5`  
    - MetaEditor **F7**  
    - Attach BTCUSD H1; verify closed-bar non-repaint and logger CSV  

11. **Docs**  
    - Update `mql5/README.md` buffer table + Wave B BTC observe recipe (this memo + optional `WAVE-B-OBSERVE.md` section)  
    - Ensure `Mt5ArchBridge` `InpSymbols` includes verified `BTCUSD` for bridge candles  

12. **Observe discipline**  
    - Journal **1–2 weeks** only  
    - Retune thresholds only after **trade-count gates** — not rarity threshold sweeps  

**Out of scope for this order:** any `OrderSend` EA, Python strategy port, risk manager.

---

## 10. Wave B chart recipe for BTCUSD

### 10.1 Terminal setup

| Setting | Value |
|---------|--------|
| Broker prefix | Active broker with `BTCUSD` (e.g. Vantage `~/.mt5-vantage`) |
| Symbol | **BTCUSD** (verify in Market Watch; add aliases only if broker uses them) |
| Timeframe | **H1** |
| Indicator | Navigator → Indicators → **BtcTrendPullback** |
| Look for | EMA50/200 stack, ATR bands, lime pullback/continuation arrows under bullish H4 bias |
| Optional EA | **ForexSignalLogger** (Algo Trading green) with inputs in §8 |
| Bridge | `Mt5ArchBridge` `InpSymbols` includes `BTCUSD` |
| Template | Save chart template after first good layout |

**Do not** attach any trading EA that places orders.

### 10.2 Install / compile

```bash
cd ~/Projects/trading/mt5-arch-integration
./scripts/18-install-forex-indicator.sh   # after script lists BtcTrendPullback.mq5
# MetaEditor: open Indicators/BtcTrendPullback.mq5 → F7
# Optional: Experts/ForexSignalLogger.mq5 → F7 if not already built
```

### 10.3 Bridge smoke (read-only)

```bash
set -a; source config/brokers/vantage.env; set +a   # or fpmarkets.env
uv run mt5-arch symbols BTCUSD --json
uv run mt5-arch candles BTCUSD --tf H1 --count 5 --json
```

### 10.4 What to journal (1–2 weeks)

- [ ] Markers align with discretionary long pullbacks you would take under H4 stack?  
- [ ] Too many signals in dead ATR% regimes? (raise `InpMinAtrPct`)  
- [ ] Continuation arrows chasing extensions? (tighten `InpMaxEma50ExtensionPct`)  
- [ ] Shorts only when H4 is clearly bearish stack?  
- [ ] Weekend/maintenance gaps: first H1 bars after reopen — any garbage signals?  
- [ ] CSV row count vs visual markers (edge-trigger + closed-bar)  
- [ ] Server time vs wall clock for any future maintenance blackouts  

After notes: retune only if **sample size** is adequate — do not reopen multi-AND rarity.

### 10.5 Session / gap mental model (operator)

Crypto is notionally 24/7; retail BTCUSD CFDs still have broker maintenance, weekend thinning, wider spreads, and Sunday reopen gaps. Prefer H4 regime + H1 closed entries; skip or distrust first bars after abnormal gaps until structure re-forms. Server time is often UTC+2/+3 — map schedules to **server clock**, not London open.

---

## 11. Non-goals and open questions

### 11.1 Non-goals

- `OrderSend` / auto-trade / risk manager / lot sizing in this indicator or repo  
- Funding rates, open interest, exchange true volume  
- HFT / sub-minute / market-making designs  
- Full Python strategy engine port (structural layers only)  
- Triple-AND OHLCV regime router or BTC/4h ultra-rare entries  
- FX session gates (Asian/London/NY) as BTC liquidity model  
- `FxPipSize` / pip spread gates / pip arrow offsets  
- Mandatory Fib golden-zone / pivot swing machine  
- Telegram bots, TimescaleDB, agent orchestration in this repo  
- Live smoke orders without explicit live flag + user consent  
- Treating logger CSV under `forex_signals/` as a finished BTC product path without BTC-aware thresholds  

### 11.2 Open questions

| # | Question | Suggested default until decided |
|---|----------|----------------------------------|
| 1 | Exact panic-block combinatorics (RSI alone vs RSI∧under-EMA200 vs ATR% alone)? | Require stress **and** `close < ema200` for long veto |
| 2 | VWAP anchor: session vs rolling N bars when enabled? | Rolling N on chart TF; document session if broker day boundary is clean |
| 3 | Short mirror: full parity with long or reduced feature set? | Full mirror under HTF −1; keep edge-trigger |
| 4 | `InpMaxSpread` in price vs ATR fraction — implement in indicator, logger, or both? | Logger off (`0`); indicator optional later |
| 5 | Deep-reclaim default on after observe? | Stay **false** until journal shows need |
| 6 | D1 HTF alternative for slower swing observe? | Input already allows `PERIOD_D1`; recipe stays H4 |
| 7 | Share `forex_signals/` CSV dir vs `btc_signals/`? | Reuse existing path for Wave B; rename only if tooling requires |
| 8 | BB squeeze visual layer (crypto-agent volatility_squeeze) in v2? | Out of v1; do not AND into entry |
| 9 | Multi-symbol (ETH etc.) later? | Name stays BTC-focused; params may work on other CFDs but not a goal |
| 10 | Sizing formula lives where? | Agent / external; ATR stop guide is visual only here |

### 11.3 Sizing notes (for downstream agents — not this indicator)

Fixed fractional risk with ATR-defined stop:  
`SL ≈ k×ATR(14)` on entry TF (*k* typically 1.5–2.5 on BTC H1).  
`lots ≈ risk_money / (SL_price_distance × tick_value/tick_size)`, clamp to broker min/step/max.  
High ATR% → wider stops → smaller size automatically. **Never** fixed-pip FX stops.  
Cap concurrent risk around weekend/maintenance; optional reduce size when spread > fraction of ATR.

---

## 12. Sources

### 12.1 crypto-agent (research + structure)

| Path | Use |
|------|-----|
| `/home/yderf/Projects/trading/crypto-agent/src/strategy/trend_pullback.py` | Core pullback / recovery / continuation grammar |
| `/home/yderf/Projects/trading/crypto-agent/src/features/technical.py` | Feature definitions (EMA, RSI, ATR%, MACD, VWAP, …) |
| `/home/yderf/Projects/trading/crypto-agent/docs/INDICATORS.md` | Indicator inventory |
| `/home/yderf/Projects/trading/crypto-agent/research/DECISION_ABANDON_BTC_REGIME.md` | Failed ultra-selective regime decision |
| `/home/yderf/Projects/trading/crypto-agent/research/RESEARCH_FINDINGS.md` | Research outcomes |
| `/home/yderf/Projects/trading/crypto-agent/research/mtf_btc_eth_template.yaml` | MTF template (historical) |
| `/home/yderf/Projects/trading/crypto-agent/docs/MTF_STRATEGY_GUIDE.md` | MTF architecture notes |
| `/home/yderf/Projects/trading/crypto-agent/src/strategy/volatility_squeeze.py` | Squeeze visuals (v2 candidate; not v1 entry AND) |
| `/home/yderf/Projects/trading/crypto-agent/src/strategy/panic_block_ma.py` | Panic-block / risk-off patterns |
| `/home/yderf/Projects/trading/crypto-agent/README.md` | Project overview |

### 12.2 Internal (this repo)

| Path | Use |
|------|-----|
| `AGENTS.md` | Platform-only boundary; safe ops |
| `mql5/Indicators/ForexHtfPivotsFib.mq5` | Buffer/logger/non-repaint reference implementation |
| `mql5/Experts/ForexSignalLogger.mq5` | `iCustom` → CSV/Print contract |
| `mql5/Include/ForexUtils.mqh` | Asset-agnostic pure helpers only (EMA/ATR/RSI/TrueRange/pivots); **avoid** pip/session BTC misuse |
| `mql5/README.md` | Install + buffer tables (update for BTC) |
| `docs/FOREX-MT5-ROADMAP.md` | Waves B→D observe-before-live |
| `docs/research/WAVE-B-OBSERVE.md` | Observe checklist; BTC bridge export note |
| `docs/research/ALGO-TRADING-BTC-GOLD-FOREX.md` | Cross-asset algo context |
| `docs/research/PHASE0-DISCOVERY.md` | Broker/symbol discovery |
| `scripts/18-install-forex-indicator.sh` | Install path into Wine prefix |
| `mql5/Mt5ArchBridge.mq5` | Symbol list for candle export |

### 12.3 Market / platform references (external)

Contextual only — CFD volume, ATR stops, VWAP pullbacks, weekend trading limits:

- MetaTrader volumes help: https://www.metatrader5.com/en/terminal/help/indicators/volume_indicators/volumes  
- Tick volume vs real volume discussions (MT5 CFD limitations)  
- ATR-based stops / position sizing for CFDs (industry practice; sizing is **not** implemented in this indicator)  
- VWAP pullback strategy literature (session/rolling mean reversion — optional soft gate)  
- Weekend/holiday CFD trading constraints (broker-specific books)

---

## Appendix A — Buffer map vs ForexHtfPivotsFib

| Index | ForexHtfPivotsFib | BtcTrendPullback |
|------:|-------------------|------------------|
| 0 | EMA50 | EMA50 |
| 1 | EMA200 | EMA200 |
| 2 | Long arrow | **ATR lower stop-guide** |
| 3 | Short arrow | **ATR upper stop-guide** |
| 4 | Fib 61.8 | **Long arrow** |
| 5 | Fib 78.6 | **Short arrow** |
| 6 | Swing direction | **HTF_bias** |
| **7** | **Signal** | **Signal** (same logger contract) |

Arrows move to 4/5 so ATR guides occupy continuous plot slots 3–4 (indices 2–3). **Signal stays at 7** for zero logger rewrites beyond indicator name.

---

## Appendix B — Design JSON snapshot (canonical defaults)

For tooling and diff checks; human sections above are authoritative if prose and JSON ever drift.

- **name:** `BtcTrendPullback`  
- **chart_tf:** H1 · **htf_tf:** H4  
- **logger_compatible:** true · signal buffer **7** · shift **1**  
- **VWAP:** default off · **shorts:** HTF-gated · **edge-trigger:** default on  
- **Deep reclaim:** default off · **panic-block:** default on  

---

*End of design draft — 2026-08-04. Implement scaffold next; observe before any automation.*
