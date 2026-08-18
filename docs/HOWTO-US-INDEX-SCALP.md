# How to use: UsIndexSessionScalp

**Indicator:** `MQL5/Indicators/UsIndexSessionScalp.mq5`
**Version covered:** 1.40
**Role:** US30 / US100 **scalp** overlay — session boxes, NY cash opening range, VWAP, EMA 9/21, closed-bar confluence markers.
**Not an EA:** does not place orders. Optional journal via `ForexSignalLogger`.

Design freeze: [US-INDEX-SESSION-SCALP-DESIGN.md](research/US-INDEX-SESSION-SCALP-DESIGN.md).

---

## 1. What you see

| Layer | What | Purpose |
|-------|------|---------|
| **London / NY opens** | Blue / gold **vertical lines** + labels (Tokyo off by default) | Session geometry (filled boxes off — they hid candles) |
| **15:45 ET vline** | Dark orange | Flatten / no-overnight reminder |
| **OR high / low** | Aqua box + dotted **ORH/ORL** lines | First 15 minutes of NY cash — levels stay after 09:45 |
| **NY VWAP** | White | Session mean from cash open |
| **EMA 9 / 21** | Blue / orange | Scalp stack |
| **PDH / PDL** | Red / green dashes | Prior ET-date range |
| **Markers** | Lime ▲ / red ▼ | AND confluence on **closed** bars |
| **Panel** | `Comment` (Wine-safe) | Session, offset, OR, VWAP, last signal |

**iCustom signal buffer: `8`** (`+1` long, `−1` short, `0` flat).

---

## 2. Install and compile

```bash
cd ~/Projects/trading/mt5-arch-integration
WINEPREFIX=~/.mt5-fpmarkets ./scripts/18-install-forex-indicator.sh
```

The install script copies into **every** existing prefix it finds. Set `WINEPREFIX` when you only care about one terminal. Do **not** start a second `terminal64.exe` in that prefix — one install, one terminal.

MetaEditor **F7** order (or headless `/compile`, below):

1. `Include/IndexSessionUtils.mqh` and `Include/IndexM5Export.mqh` (pulled in automatically)
2. `Indicators/UsIndexSessionScalp.mq5`
3. Optional live-safe dump: `Scripts/ExportUsIndexM5.mq5` (does **not** kill the terminal)
4. Confirm panel shows **v1.40**

Wine often will not reload an already-attached `.ex5`. Remove the indicator and reattach after compile.

Headless compile (FP prefix; do not launch another terminal):

```bash
WINEPREFIX=~/.mt5-fpmarkets
ME="$WINEPREFIX/drive_c/Program Files/FP Markets MT5 Terminal/MetaEditor64.exe"
cd "$WINEPREFIX/drive_c/Program Files/FP Markets MT5 Terminal/MQL5/Indicators"
wine "$ME" /compile:"UsIndexSessionScalp.mq5" /log
```

`wine` exit 1 after a clean compile is normal. Read the `.log` for `0 error(s)`.

---

## 3. Chart recipe

| Setting | Value |
|---------|--------|
| Symbol | **US100 / NAS100 / USTEC** (primary) or **US30 / DJ30.r** (FP / Vantage) |
| TF | **M5** (M1 OK; M15 OK; avoid H1) |
| Mode | Scalp only — do not hold into the 15:45 ET line |
| One tab per TF | Same Wine rule as HTF Fib: switch tabs, do not spam the TF toolbar |

### Attach

1. Open the index chart (tab, not undocked under Wine).
2. Navigator → **UsIndexSessionScalp** → drag onto chart.
3. If session boxes do not sit on 09:30 ET, set **Server UTC offset hours** (Vantage is often `+2` or `+3`). Panel prints the auto offset.
4. Optional: `ForexSignalLogger` on the same chart (compiled on FP 2026-08-18; **not** auto-attached — [§12b](#12b-ea-observe--forexsignallogger-compiled-not-auto-attached)):
   - `InpIndicatorName=UsIndexSessionScalp`
   - `InpSignalBuffer=8`
   - `InpMaxSpreadPips=0` (index gate is **points**, inside the indicator)
   - Or Inputs → Load `Presets/ForexSignalLogger-UsIndexSessionScalp.set`

### Confirm

```text
UsIndexSessionScalp v1.40
ET     12:10   session NY cash   srv +3h
Family ORB+VWAP+EMA  window-to 11:30
Signal flat  | outside_entry_window | no orders
```

---

## 4. Signal rules (frozen)

A marker fires on a **closed** bar only when all of these hold:

- Bar open in **[09:45, 11:30) ET**
- NY 15m opening range is **complete** (not during 09:30–09:45)
- Close beyond OR (not a wick)
- Close on the VWAP side of the break
- EMA9 stacked with the break
- ATR% above the dead-lunch floor
- Not Friday ≥ 14:00 ET
- At most one signal per ET date
- Live spread ≤ cap (`InpMaxSpreadPoints=0` auto: US100 **200** pt / US30 **80** pt). FP US100 cash is often ~60 pt — v1.00’s 50 cap blocked every bar.

Do not retune these to chase a screenshot.

---

## 5. Buffers (`iCustom`)

| Index | Content |
|------:|---------|
| 0 | EMA9 |
| 1 | EMA21 |
| 2 | NY cash VWAP |
| 3 | OR high (EMPTY until complete) |
| 4 | OR low |
| 5 | Long arrow |
| 6 | Short arrow |
| 7 | Session id (0 off / 1 Tokyo / 2 London / 3 NY / 4 overlap) |
| **8** | **Signal (+1/−1/0)** |
| 9 | ATR |

```mql5
double sig[];
ArraySetAsSeries(sig, true);
CopyBuffer(handle, 8, 1, 1, sig);  // last closed bar
```

---

## 6. Safety

- Never `OrderSend`. This repo’s charter: observe first.
- Wine: objects are ChartID-keyed and are **not** mass-deleted on timeframe change (HTF Fib freeze lesson).
- `tick_volume` is not exchange volume. VWAP is a CFD proxy, same as `BtcTrendPullback`.

---

## 7. Offline flatten replay (no orders)

Frozen combo only. Holdout starts **2026-06-01** (locked; not for selection).

```bash
python3 scripts/us_index_session_backtest.py \
  --hc ~/.mt5-fpmarkets/drive_c/Program\ Files/FP\ Markets\ MT5\ Terminal/Bases/FPMarketsSC-Live/history/US100/cache/M5.hc \
  --symbol US100 --server-utc-offset 10800 \
  --out results/us_index_session_scalp_backtest.json
```

First run (2026-08-18): US100 PF **0.80** all / **0.96** holdout — **promote=no**. Write-up: [us_index_session_scalp_backtest.md](../results/us_index_session_scalp_backtest.md).

Do not retune OR / EMA / the entry window on that CSV.

---

## 8. Develop screen (2026-08-18) — goals missed

Full grid `us_index_session_develop_v1`: **1,728** configs, holdout locked at **2026-06-01**. Write-up: [us_index_session_autoresearch.md](../results/us_index_session_autoresearch.md).

Goals were **median trade-day ≥ 1%** and **median month ≥ 20%** on a $10k / 1-lot book. **0** develop-eligible configs hit both. Best develop: OR 5 / EMA 8/21 / window to 10:30 / ATR 1.0×SL 1.5×TP — **0.40%** median day, **1.89%** median month; holdout median day **−0.28%**. **promote=no.**

Defaults stay frozen (OR 15, EMA 9/21, window to 11:30). Optional observe knobs only:

| Input | Frozen default | Research-candidate observe |
|-------|----------------|----------------------------|
| `InpOrMinutes` | 15 | 5 |
| `InpEmaFast` / `InpEmaSlow` | 9 / 21 | 8 / 21 |
| `InpEntryEndHour` / `InpEntryEndMinute` | 11 / 30 | 10 / 30 |
| `InpShowAtrStops` | false | true (SL 1.0 / TP 1.5 ATR) |

Do not expand this grid or retune on holdout to chase 1%/20%.

---

## 9. Playbook families (v1.40, observe only)

Second screen `us_index_session_playbook_v2`: VWAP bounce + EMA/MACD. Write-up: [us_index_session_playbook_v2.md](../results/us_index_session_playbook_v2.md).

**0 / 205** develop-eligible configs hit 1%/day and 20%/month. Best VWAP bounce develop: **0.31%** median day, holdout PF **0.81**. Best EMA/MACD develop: **0.22%** median day, holdout PF **0.72**. **promote=no.**

`InpFamily` default stays **frozen ORB**. Optional observe (playbook text, not the develop winner):

| `InpFamily` | Chart inputs to set by hand |
|-------------|-----------------------------|
| `IDX_FAM_VWAP_BOUNCE` | Entry end 10:30 · RSI 14 · 75/25 · ATR dev 1.0 |
| `IDX_FAM_EMA_MACD` | EMA 5/20 · MACD 12/26/9 · `InpCrossOnly=true` · entry end 10:30 |

Still no orders. Do not retune on holdout or “trade the US30 transfer.”

---

## 10. Structure screen (v3) — news skipped, goals missed

`us_index_session_structure_v3`: liquidity sweep, M5 FVG, US100/US30 divergence. Write-up: [us_index_session_structure_v3.md](../results/us_index_session_structure_v3.md).

**0 / 129** develop-eligible configs hit 1%/20%. Best sweep develop: **0.17%** median day; holdout median day **−0.45%**. **promote=no.**

`macro_news_fix_api` was **not** run. The `manual-trading-agent` calendar ends 2025-04-07, timestamps are Tehran (not 08:30 ET), and that repo’s FX surprise-drift is DISCARD.

---

## 11. v4 screen — regime / proxy-CVD / POC (goals missed)

`us_index_session_v4`. Lock: [us_index_session_v4_lock.json](../results/us_index_session_v4_lock.json). Write-up: [us_index_session_v4.md](../results/us_index_session_v4.md).

Select before **2026-06-01**. New holdout from **2026-07-01**. June unused. Slippage kept at 10 pt/side.

**0 / 105** develop-eligible configs hit 1%/20%. Best (vol-regime OR + ATR 1.0/1.5): develop **0.31%** median day; holdout **−0.40%**. True bid/ask CVD and HMM were **skipped** (no TimescaleDB / no aggressor ticks). **promote=no.**

v3/v4 families are **Python-only**. They are not `InpFamily` modes on the chart. The live overlay stays frozen ORB (optional v2 observe).

---

## 12. What is actually wired into MT5

Full operator inventory of the live Wine/MT5 stack: [MT5-INTEGRATION-CAPABILITIES.md](MT5-INTEGRATION-CAPABILITIES.md).

| Layer | File | Live role |
|-------|------|-----------|
| Overlay | `Indicators/UsIndexSessionScalp.mq5` v1.40 | Session boxes, NY OR, VWAP, EMA, buffer **8**. Default family = frozen ORB. Optional `InpFamily` = VWAP bounce / EMA+MACD. |
| Clock / spread | `Include/IndexSessionUtils.mqh` | DST ET/London/Tokyo; point spread gate |
| M5 dump | `Include/IndexM5Export.mqh` | If `MQL5/Files/mt5_arch/export_us_index.request` exists, the indicator writes `history_US100_M5.csv` / `history_US30_M5.csv` and deletes the request. No `OrderSend`. Does not kill the terminal. |
| Standalone dump | `Scripts/ExportUsIndexM5.mq5` | Same dump, drag-and-drop. **Do not** use `ExportInstrumentHistory.mq5` on an open prefix — that script shuts the terminal. |
| Logger | `Experts/ForexSignalLogger.mq5` | `InpIndicatorName=UsIndexSessionScalp`, buffer **8**, `InpMaxSpreadPips=0`. CSV under `MQL5/Files/forex_signals/`. Never orders. Compiled on FP; **not** live-attached — [§12b](#12b-ea-observe--forexsignallogger-compiled-not-auto-attached). |
| Install | `scripts/18-install-forex-indicator.sh` | Copies includes / indicator / logger / export script into Wine `MQL5/` |

Python screens (`us_index_session_autoresearch*.py`, v3–v5) read the exported CSV or the FP `M5.hc` cache. They do **not** attach to the chart.

Do not promote from the overlay. Do not attach an order EA.

---

## 12b. EA observe — ForexSignalLogger (compiled, not auto-attached)

**2026-08-18.** Used the existing log-only EA, not a new trading expert. Overlay defaults stay frozen `ny_cash_orb_vwap_ema_flat` / UsIndexSessionScalp **v1.40**. **promote=no.**

| Item | Result |
|------|--------|
| EA | `mql5/Experts/ForexSignalLogger.mq5` (never `OrderSend`) |
| Inputs | `InpIndicatorName=UsIndexSessionScalp` · `InpSignalBuffer=8` · `InpSignalShift=1` · `InpMaxSpreadPips=0` · CSV on |
| Preset | `mql5/Presets/ForexSignalLogger-UsIndexSessionScalp.set` (copied to `MQL5/Presets/` by `18-install-forex-indicator.sh`) |
| Compile | FP prefix MetaEditor `/compile` from `MQL5/Experts` — **0 errors, 0 warnings**, 491 ms. `wine` exit 1 is normal. `.ex5` written 2026-08-18 16:27. |
| Live attach | **No.** Logger is compiled only. |
| CSV / Experts | `MQL5/Files/forex_signals/` still empty. Journal has **no** `ForexSignalLogger ON` line. Only live EA: `Mt5ArchBridge` on US500 H1. |

**Live FP chart (left alone):** Default profile `chart05.chr` is **US100 M15** with `UsIndexSessionScalp.ex5` (frozen OR 15 / EMA 9/21). No `<expert>` block. Open book at compile time was **3× NZDCHF.r** (bridge `positions.json`); the US100 tab still has historical autotrade objects. One `terminal64.exe /portable` in `~/.mt5-fpmarkets` — not restarted.

**Why attach was refused:** injecting `<expert>` into the live `.chr` does not apply until a profile reload / terminal restart, and the running terminal overwrites those files from memory. Applying a `.tpl` would replace the overlay. Wine click-through on workspace 6 is unreliable and could hit the live book. No second `terminal64`. No `ExportInstrumentHistory.mq5`. No `19-run-htf-fib-backtest.sh` / `KILL_EXISTING=1`. No `ForexHtfFibTester` on this prefix (that EA *does* `OrderSend` in tester). No new `UsIndexSessionLogger` wrapper — the existing logger is enough.

### Navigator attach (human, when convenient)

Do this on the **already-open** US100 tab. Do not start another terminal. Do not attach `ForexHtfFibTester`.

1. Navigator → **Expert Advisors** → **ForexSignalLogger** → drag onto the US100 chart (same tab as `UsIndexSessionScalp`).
2. Inputs → **Load** `ForexSignalLogger-UsIndexSessionScalp.set`, or set the four fields in the table above by hand.
3. Algo Trading is already green for `Mt5ArchBridge`. Leave it; the logger still never sends orders.
4. Experts tab should print `ForexSignalLogger ON | US100 … | ind=UsIndexSessionScalp buf=8 | NO ORDERS`.
5. A CSV appears only after a **non-zero closed-bar** signal: `MQL5/Files/forex_signals/US100_PERIOD_M15.csv` on the current M15 tab (or `…_PERIOD_M5.csv` if you switch tabs). Flat days stay empty.

Still **promote=no**. Do not treat a journal line as a live-go.

---

## 13. One-shot cost/size diagnostic (2026-08-18)

Locked **before** the run: [us_index_session_v4_cost_size_once_lock.json](../results/us_index_session_v4_cost_size_once_lock.json). Write-up: [us_index_session_v4_cost_size_once.md](../results/us_index_session_v4_cost_size_once.md).

This is a **replay**, not a search. It re-runs the frozen flatten combo and the already-selected v4 develop winner on five pre-registered books (locked 1 lot / 10 pt; slip 0; 2 lots; 5 lots; slip 0 + 5 lots). **Timescale / M1 / US500 were not added** — no tick store, no new export, no US500 in any prefix.

**0 / 5** books hit both goals. Zeroing slippage moves median day by ~0.002 pp. Five lots scales the same ~0.3% v4 develop day to 1.53% (daily only; month 7.5%) and the holdout to **−2.0%**. Frozen flatten stays a loser (PF 0.72). **promote=no.** The locked book is unchanged.

---

## 14. v5 screen — gap / HTF lock / US30 follow (goals missed)

`us_index_session_v5`. Lock: [us_index_session_v5_lock.json](../results/us_index_session_v5_lock.json). Write-up: [us_index_session_v5.md](../results/us_index_session_v5.md).

Select before **2026-06-01**. Holdout from **2026-07-01**. Book unchanged. Built from clocks already in this repo, BTC/XAU completed-HTF join, and US30 M5 on disk — **not** the XAU London-FX leak and **not** v3 divergence.

**0 / 43** develop-eligible configs hit 1%/20%. Best (H4-locked OR + ATR 1.0/1.5): develop **0.40%** median day / PF 2.23; holdout **−0.46%** / PF 0.60. Gap fade and US30 follow are weaker in-sample and still negative on holdout. **promote=no.** Stay off the chart.

---

## 15. v6 screen — daily regime + London XAU gate (goals missed)

`us_index_session_v6`. Lock: [us_index_session_v6_lock.json](../results/us_index_session_v6_lock.json). Write-up: [us_index_session_v6.md](../results/us_index_session_v6.md).

Select before **2026-06-01**. Holdout from **2026-07-01** (July–August already sat inside v4/v5 holdout aggregates — cleaner, not virgin). Book unchanged. Daily Hurst/ADX/ATR AND-gate on **completed ET-days** plus a causal FP `XAUUSD.r` H1 London window (07:00–09:00 **ET**, not server `{7,8,9}`). EUR/GBP skipped (stale cache / Vantage clock). US30 not reused.

**0 / 4** develop-eligible configs hit 1%/20%. Regime family: **0 / 128** eligible (AND-gate starved; best raw n=5). Best (London XAU gate, 0.5 ATR, EMA21 trail): develop **−0.038%** median day / PF 1.49; holdout **−0.19%** / PF 3.14. Mean day is slightly positive; the median is not. **promote=no.** Python-only — stay off the chart.

---

## 16. v7 screen — IB false-break + M5 z-score (goals missed)

`us_index_session_v7`. Lock: [us_index_session_v7_lock.json](../results/us_index_session_v7_lock.json). Write-up: [us_index_session_v7.md](../results/us_index_session_v7.md).

Select before **2026-06-01**. Holdout from **2026-07-01** (July–August already sat inside v4–v6 holdout aggregates — cleaner, not virgin). Book unchanged. Pivot off daily Hurst/ADX/ATR: 60m IB false-break (sweep, then **next** M5 close back inside; IB knowable at 10:30) and M5 typical-price z-score plus tick-volume spike (μ/σ/Vμ from the prior 12 or 24 closed bars **excluding** the signal bar). Python-only — stay off the overlay.

**0 / 13** develop-eligible configs hit 1%/20%. IB family: **0 / 8** eligible (best raw PF 0.93, −0.32% day). Best (z 2.5, vol_k 1.5, window 12, [09:45, 15:00), one/day): develop **+0.17%** median day / PF 2.98; holdout **−0.28%** / PF 1.48. **promote=no.**

---

## 17. v8 screen — H1 squeeze + H4 fib pullback (goals missed)

`us_index_session_v8`. Lock: [us_index_session_v8_lock.json](../results/us_index_session_v8_lock.json). Write-up: [us_index_session_v8.md](../results/us_index_session_v8.md).

Leave M5 scalping. Select before **2026-06-01**. Holdout from **2026-07-01** (July–August already sat inside v4–v7 holdout aggregates — cleaner, not virgin). Book unchanged. Data is native FP `H1.hc` / `H4.hc` / `Daily.hc` via `read_mt5_hc` (not the M5 request-file dump). Live terminal not attached. Python-only — stay off the overlay.

**0 / 0** develop-eligible configs (none reached 40 trades with net>0). **0 / 32** hit 1%/20%. Best raw (H1 squeeze, BB 2.0 / KC 1.5, one/day): develop **6** trades · PF 1.20 · **−1.09%** median day; holdout **2** losers · **−1.19%**. H4 fib pullback fires more (20 develop trades) and loses (PF 0.51, **−1.74%** day). **promote=no.**
