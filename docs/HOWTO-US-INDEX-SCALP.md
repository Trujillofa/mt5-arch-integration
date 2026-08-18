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
./scripts/18-install-forex-indicator.sh
```

MetaEditor **F7** order:

1. `Include/IndexSessionUtils.mqh` (pulled in automatically)
2. `Indicators/UsIndexSessionScalp.mq5`
3. Confirm panel shows **v1.40**

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
4. Optional: `ForexSignalLogger` on the same chart:
   - `InpIndicatorName=UsIndexSessionScalp`
   - `InpSignalBuffer=8`
   - `InpMaxSpreadPips=0` (index gate is **points**, inside the indicator)

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
