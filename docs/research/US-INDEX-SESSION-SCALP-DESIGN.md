# UsIndexSessionScalp — Design Memo (US30 / US100)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Status** | Overlay shipped; flatten replay **does not pay**; develop screen **missed 1%/20%** (promote=no) |
| **Indicator** | `UsIndexSessionScalp` v1.40 |
| **Family** | `ny_cash_orb_vwap_ema_flat` (defaults frozen) |
| **Repo boundary** | Platform / research overlay: visual + `iCustom` + logger — **no** `OrderSend` |
| **Primary chart** | US100 / NAS100 / USTEC **M5** (US30 / DJ30.r alternate) |
| **Logger** | `ForexSignalLogger` · `InpSignalBuffer=8` · `InpMaxSpreadPips=0` |
| **promote / live_go** | **no / false** |
| **Develop screen** | **executed** `us_index_session_develop_v1` — 0/615 hit goals |

---

## 1. Why this exists

XAU session families in this repo are **SCREEN_FAIL** or idle. FX directional TA (naked ORB, trend-pullback) was **closed** in `manual-trading-agent` (gross PF ~1.0–1.07). Those results do **not** transfer a kill to US equity-index CFDs: US30/US100 have a **real cash open at 09:30 America/New_York**. FX majors do not.

This is a new instrument family. The indicator is Wave B observe grammar, not a promote path.

## 2. What was read (all of `~/Projects/trading`)

| Source | Kept | Rejected as default |
|--------|------|---------------------|
| `ctrader-trading-agent` `SessionClock` | DST-safe local clocks; skip first noisy minutes; Friday EOD | FX currency z-score / pair selection |
| `ctrader` session-momentum | Spread vs reward discipline | Pip-centric SL/TP |
| `manual-trading-agent` `session_orb` | Causal OR (known only after last OR bar closes); close-confirm, not wick | Naked FX ORB (closed lane) |
| `manual-trading-agent` `instruments.py` | NASDAQ / NQ=F as index_futures; points not pips | Globex 00–21 UTC window as the *entry* clock (cash 09:30 ET is tighter) |
| `ForexIndicatorTemplate` | Prior-day H/L visual; Comment panel; closed-bar signals | FX 20/50/200 swing stack; pip spread gate |
| `ForexHtfPivotsFib` | ChartID object keys; **no** `ObjectsDeleteAll` on `CHARTCHANGE` | Fib golden-zone as a scalp trigger |
| `BtcTrendPullback` | ATR% liveliness; VWAP typical×tick_volume; ATR arrow offset | H4 EMA50/200 crypto grammar; FX session model |
| `daily_stock_analysis` | Cash session 09:30 ET | Daily stock scanner |
| XAU charters | Freeze-before-peek; costs; no overnight if swap unmodeled | Reviving TOD / Donchian / bb_rsi / prior_day_high_break |

No existing US30/US100 scalp indicator existed in those repos. The combo below is **synthesized and frozen**, not selected by peeking index history.

## 3. Frozen combo

**`ny_cash_orb_vwap_ema_flat`** — AND, not a search:

1. **Draw** London (08:00–17:00 Europe/London), NY cash (09:30–16:00 ET), plus a 15:45 ET flatten vline. Tokyo vline is off by default (overnight noise on a NY-scalp zoom).
2. **Opening range** = first **15 minutes** of NY cash. Knowable on the first bar whose open ≥ 09:45 ET.
3. **Session VWAP** from the first NY-cash bar of that ET date (typical × `tick_volume`, floor 1).
4. **EMA 9 / 21** on the chart TF (scalp stack, not 20/50/200).
5. **Entry window** `[09:45, 11:30)` ET only. Asia and lunch are off.
6. **Long:** close > OR high **and** close > VWAP **and** EMA9 > EMA21 **and** ATR% floor.
7. **Short:** mirror. Wick-only breaks do not count.
8. **One signal per ET date.** Friday: no new entries from 14:00 ET.
9. **Spread gate in points** (live bar only). `0` = auto (US100 **200** / US30 **80**). FP US100 cash is often ~60 pt.
10. **Force-flat visual at 15:45 ET** — not an EA close.

Why this AND-gate (not OR-only, not VWAP-only, not EMA-only):

| Layer | Alone | With the others |
|-------|-------|-----------------|
| OR break | Failed as FX directional TA; on indices it is the cash-open range | Defines the first accepted print |
| VWAP | Mean-reversion without a session event | Institutional side of the open drive |
| EMA 9/21 | Lagging chop | Scalp timing so we do not fade a still-stacked open |

US100 is the documented primary (cleaner trend, higher ATR). US30 is supported; it mean-reverts more around VWAP.

## 4. Causality

Python source of truth: `scripts/us_index_session_core.py`.

- OR high/low are **NaN / EMPTY_VALUE** until the first bar that opens at or after 09:45 ET.
- Signals use only bars `0..i` on the close of `i`.
- Forming bar is never a signal (`InpSignalOnClose`).
- Do not re-derive the OR stamp at 09:30 — that is lookahead.

## 5. Clock

Sessions are **local TZ**, not raw broker hours (`ForexUtils` FX defaults stay untouched).

MQL5 converts server bar time → UTC via `TimeCurrent()-TimeGMT()` (override `InpServerUtcOffsetHours` if boxes miss 09:30 ET). Historical DST of the *broker* offset is approximate; US/UK DST rules are explicit.

## 6. What this is not

- Not a charter-sealed XAU family. Do not run `xau_sealed_family_cycle` on it.
- Not permission to `--live` or attach an order EA.
- Not a develop-window grid. Defaults are frozen; do not retune OR minutes / EMA / window to chase a CSV.
- Not HTF Fib and not BtcTrendPullback. Do not mix their signal buffers.

## 7. First replay (2026-08-18)

Executed: `scripts/us_index_session_backtest.py` on FP `M5.hc` (spread in cache). Holdout locked at **2026-06-01**. Write-up: `results/us_index_session_scalp_backtest.md`.

US100 PF 0.80 all / 0.96 holdout. US30 pre-holdout PF 1.20 **fails** holdout (0.50). **promote=no.**

A later screen, if ever authorized, is a **new** `family_id` with freeze-before-peek — not a retune of this combo on the same CSV.

## 8. Develop screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch.py`. Lock: `results/us_index_session_develop_lock.json`. Write-up: `results/us_index_session_autoresearch.md`.

1,728 configs. Holdout **2026-06-01** unused for selection. Goals: median trade-day ≥ 1%, median month ≥ 20% on $10k / 1 lot. **0** develop-eligible configs hit both. Best develop (OR 5 / 8/21 / 10:30 / ATR 1.0/1.5) is 0.40% / 1.89%; holdout median day −0.28%. Flatten-15:45 never ranks.

v1.30 adds optional entry-end + ATR SL/TP *guides*. Frozen defaults are unchanged. Do not promote from this screen.

## 9. Playbook screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v2.py`. Lock: `results/us_index_session_playbook_v2_lock.json`. Write-up: `results/us_index_session_playbook_v2.md`.

New families: `ny_cash_vwap_bounce_rsi`, `ny_cash_ema_macd`. 528 configs. Holdout unused for selection. **0** develop-eligible configs hit 1%/20%. Best bounce develop 0.31% / holdout PF 0.81. Best EMA/MACD develop 0.22% / holdout PF 0.72. US30 transfer is evaluation-only.

v1.40 adds optional `InpFamily` observe modes. Default remains frozen ORB. Do not promote.
