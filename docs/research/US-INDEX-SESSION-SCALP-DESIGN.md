# UsIndexSessionScalp — Design Memo (US30 / US100)

| Field | Value |
|-------|--------|
| **Date** | 2026-08-18 |
| **Status** | Overlay shipped; **v1–v8 screens missed 1%/20%; promote=no** |
| **Indicator** | `UsIndexSessionScalp` v1.40 |
| **Family** | `ny_cash_orb_vwap_ema_flat` (defaults frozen) |
| **Repo boundary** | Platform / research overlay: visual + `iCustom` + logger — **no** `OrderSend` |
| **Primary chart** | US100 / NAS100 / USTEC **M5** (US30 / DJ30.r alternate) |
| **Logger** | `ForexSignalLogger` · `InpSignalBuffer=8` · `InpMaxSpreadPips=0` |
| **promote / live_go** | **no / false** |
| **Develop screen** | **executed** `us_index_session_develop_v1` — 0 eligible hit goals |

> **Not XAU Phase E.** This US-index work does **not** authorize or substitute for XAU Phase E. Do **not** edit `results/xau_loop_status.md` from this lane; see that file for current XAU disposition (`RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`). Do **not** revive `AWAIT_PHASE_E_SCREEN_AUTHORIZATION`. Locks already say this is not the sealed XAU London-FX family and not `xau_sealed_family_cycle`.

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

1,728 configs. Holdout **2026-06-01** unused for selection (June is **in** this holdout; do not retcon onto the v4 split). Goals: median **trade-day** ≥ 1%, median **trade-month** ≥ 20% on $10k / 1 lot. Those medians skip calendar days with no trade. **0** develop-eligible configs hit both. Best develop (OR 5 / 8/21 / 10:30 / ATR 1.0/1.5) is 0.40% / 1.89%; holdout median day −0.28%. Flatten-15:45 never ranks.

Locked slippage is **10 MT5 points (0.01) per side**, not 10 index points. Round-trip ≈ $0.20 slip + ~$0.60 typical spread. `score_row` pins `profit_factor is None` (all winners) to 3.0 — same as a finite PF 3.

v1.30 adds optional entry-end + ATR SL/TP *guides*. Frozen defaults are unchanged. Do not promote from this screen.

## 9. Playbook screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v2.py`. Lock: `results/us_index_session_playbook_v2_lock.json`. Write-up: `results/us_index_session_playbook_v2.md`.

New families: `ny_cash_vwap_bounce_rsi`, `ny_cash_ema_macd`. 528 configs. Holdout unused for selection. **0** develop-eligible configs hit 1%/20%. Best bounce develop 0.31% / holdout PF 0.81. Best EMA/MACD develop 0.22% / holdout PF 0.72. US30 transfer is evaluation-only.

v1.40 adds optional `InpFamily` observe modes. Default remains frozen ORB. Do not promote.

## 10. Structure screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v3.py`. Lock: `results/us_index_session_structure_v3_lock.json`. Write-up: `results/us_index_session_structure_v3.md`.

Families: `ny_cash_liquidity_sweep`, `ny_cash_fvg_mitigation`, `us100_us30_divergence`. **`macro_news_fix_api` skipped** — no joinable calendar in this window; do not copy the discarded FX drift lane. 240 configs. **0** hit 1%/20%. Best sweep develop 0.17% / holdout median day −0.45%. Do not promote.

## 11. v4 screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v4.py`. Lock: `results/us_index_session_v4_lock.json`. Write-up: `results/us_index_session_v4.md`.

Select `< 2026-06-01`. Holdout `>= 2026-07-01`. June burned. Families: `vol_regime_orb`, `tick_proxy_cvd` (not bid/ask CVD), `prior_poc_reversion`. HMM / Timescale CVD skipped. 192 configs. **0** hit 1%/20%. Best develop 0.31% / holdout median day −0.40%. Costs unchanged. Do not promote.

v3/v4 stay Python-only. Chart `InpFamily` is still frozen ORB + optional v2 observe.

## 12. MT5 integration (what shipped vs what did not)

Shipped to Wine and the open FP `US100` chart:

- `UsIndexSessionScalp` v1.40 (buffer 8) + `IndexSessionUtils` + `IndexM5Export`
- Optional `ForexSignalLogger` (same buffer, `InpMaxSpreadPips=0`)
- Live-safe M5 dump via `export_us_index.request` or `ExportUsIndexM5.mq5`

Not shipped to the chart: v3 sweep/FVG/div, v4 regime/proxy-CVD/POC. Those screens missed 1%/20%; putting them on the overlay would look like a promote.

Not in this repo: TimescaleDB / aggressor ticks. Not in any prefix: US500. M1.hc exists on FP US100/US30 and was **not** exported for a chase.

## 13. One-shot cost/size diagnostic (2026-08-18)

Authorized as a **replay**, not a new search. Lock: `results/us_index_session_v4_cost_size_once_lock.json`. Write-up: `results/us_index_session_v4_cost_size_once.md`.

Replays frozen flatten + v4 develop winner only. Five books (locked / slip0 / lots2 / lots5 / both). No Timescale, no M1, no US500. **0 / 5** hit both goals. Slippage is noise; 5× lots scales the same ~0.3% develop day and a **worse** holdout. Locked book unchanged. **promote=no.**

## 14. v5 screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v5.py`. Lock: `results/us_index_session_v5_lock.json`. Write-up: `results/us_index_session_v5.md`.

Select `< 2026-06-01`. Holdout `>= 2026-07-01`. June burned. Families: `ny_cash_gap_fade_adr` (vs **prior cash close**, not the overnight print), `htf_lock_orb` (completed H4 EMA / Daily Donchian gate), `exog_us30_ny_cash_cosign_us100_follow` (US30 T* sign only). Did **not** copy XAU `{7,8,9}` / EUR+GBP, joint fade, v3 divergence, news-drift, Timescale, M1, or US500. 120 configs. **0** hit 1%/20%. Best develop 0.40% / holdout median day −0.46%. Costs unchanged. Do not promote. Stay off the overlay.

## 15. v6 screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v6.py`. Lock: `results/us_index_session_v6_lock.json`. Write-up: `results/us_index_session_v6.md`.

Architectural reset after v1–v5. Select `< 2026-06-01`. Holdout `>= 2026-07-01`. June burned. July–August is a cleaner v4/v5 holdout window, **not virgin**. Families: `daily_regime_switch` (completed-ET-day Wilder ADX + ATR percentile + R/S Hurst with locked VR fallback; momentum = 15m OR trail, MR = prior-cash-close gap fade; asymmetric exits) and `london_xau_fx_risk_gate` (FP `XAUUSD.r` H1, ET 07:00–09:00, as-of join, T* isolation). EUR/GBP skipped. Vantage H1 not joined. US30 not reused. 136 configs. **0** hit 1%/20%. Regime: 0 eligible. Best develop −0.038% median day / holdout −0.19%. Costs unchanged. Python-only. Do not promote. Stay off the overlay.

## 16. v7 screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v7.py`. Lock: `results/us_index_session_v7_lock.json`. Write-up: `results/us_index_session_v7.md`.

Intraday kinetics after v6 starvation. Select `< 2026-06-01`. Holdout `>= 2026-07-01`. June burned. July–August is a cleaner v4–v6 holdout window, **not virgin**. Families: `ib_false_breakout_fade` (60m IB knowable at 10:30; sweep then **next** M5 close back inside; target mid or opposite IB; SL ATR 1.0; flatten 15:45) and `m5_zscore_tick_vol_exhaustion` (typical-price Z vs prior W bars **excluding** `i`; vol spike vs the same Vμ; windows 12/24; sessions [09:45, 15:00) or [09:45, 11:30)). Did **not** revive daily regime, US30, XAU `{7,8,9}`, H4/Donchian AND, news-drift, Timescale, M1, or US500. 40 configs. **0** hit 1%/20%. IB: 0 eligible. Best develop +0.17% median day / holdout −0.28%. Costs unchanged. Python-only. Do not promote. Stay off the overlay.

## 17. v8 screen (2026-08-18)

Executed: `scripts/us_index_session_autoresearch_v8.py`. Lock: `results/us_index_session_v8_lock.json`. Write-up: `results/us_index_session_v8.md`.

Leave M5 scalping. Select `< 2026-06-01`. Holdout `>= 2026-07-01`. June burned. July–August is a cleaner v4–v7 holdout window, **not virgin**. Data from native FP `H1.hc` / `H4.hc` / `Daily.hc` (`read_mt5_hc`), not the M5 request-file dump. Families: `h1_volatility_squeeze_breakout` (BB⊂KC on completed H1; release + close vs prior-20 Donchian; completed Daily SMA50 slope) and `h4_impulse_fib_pullback` (`htf_fib_core.confirmed_pivots` + 61.8–78.6; fill next H1 open after H4 confirm close). 32 configs locked before peek. **0** eligible. **0** hit 1%/20%. Best raw develop −1.09% median day / holdout −1.19%. Costs unchanged. Python-only. Do not promote. Stay off the overlay.
