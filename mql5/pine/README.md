# Pine v5 ports (observe-only)

Visual / signal ports of the five in-repo custom overlays. **This repo's MQL5 is the source of truth** — not the older `manual-trading-agent` `tradingview_pivot_rsi_ema.pine` dialect.

- `//@version=5` + `indicator()` only. No `strategy()`, no `strategy.entry`, no `OrderSend`.
- **observe-only / promote=no / not a live signal.**
- **Merge ≠ deploy.** Adding these files does not install anything on OMARCHY / Wine / MT5.

Authoritative MQL5 signal indices: `mql5/Include/SignalContract.mqh`.

## Mapping

| MQL5 | Pine | Signal buffer | Known limitations |
|------|------|---------------|-------------------|
| `Indicators/ForexHtfPivotsFib.mq5` | `ForexHtfPivotsFib.pine` | **8** | No `forex_sr_levels.csv` / `.tpl` S/R import. No `htf_fib_effective_*.txt` writer. No tester H1 fallback when HTF history is empty. Pivots via `ta.pivothigh` + `request.security(..., gaps_on, lookahead_off)` ≈ confirm-bar close (not center). Wine `Comment` / `ChartObjects` → table + plots. |
| `Indicators/ForexIndicatorTemplate.mq5` | `ForexIndicatorTemplate.pine` | **9** (buffer **8** is the short arrow, not the signal) | Session hours are broker **SERVER** time in MQL5. Pine default is `syminfo.timezone` (`InpSessionTimezone=exchange`); set NY/London/UTC to match a broker. Live bid/ask spread gate is stubbed (historical TV has no MT5 spread). Prior-day H/L/O uses completed exchange `D` bars. |
| `Indicators/UsIndexSessionScalp.mq5` | `UsIndexSessionScalp.pine` | **8** | DST is **not dropped**: IANA `America/New_York` / `Europe/London` / `Asia/Tokyo` replaces `IndexSessionUtils.mqh` server-offset + US/UK DST tables. `InpServerUtcOffsetHours` unused. No `IdxSpreadPoints` on history. No `IndexM5Export`. Session boxes / GDI vlines → bgcolor + plotshape. Volume is TV `volume` vs MT5 `tick_volume`. Frozen default family still ORB. |
| `Indicators/BtcTrendPullback.mq5` | `BtcTrendPullback.pine` | **7** | HTF bias uses `request.security(lookahead_off)` = completed HTF bar (same idea as `CompletedHtfShift`). No session clock. Rolling VWAP uses chart volume, not tick volume. |
| `Indicators/BtcNySessionScalp.mq5` | `BtcNySessionScalp.pine` | **8** | **SCREEN_FAIL / observe-only / promote=no.** Session is `[08:00, 11:30)` `America/New_York`. MQL5 maps ET as server−7h (`BTC_SERVER_MINUS_SEC`) so DST tracks with the broker; Pine uses ET directly (the +7h offset is a Wine-broker convention). Not a trading signal. |

iCustom buffer tables stay in [`mql5/README.md`](../README.md). Do not retune frozen research families.

## Host-only / not ported

These overlays exist on **OMARCHY terminals only** and are **not in this repo**. Logic was not invented and is not ported:

- `GoldSessionScalp.mq5`
- `OilSessionScalp.mq5`

Also not converted (out of scope): Experts, Scripts, `Mt5ArchBridge` / ReadOnly, Broker Examples / Free Robots, third-party Telegram `TradingPro_NivelesDelDia*`.

## Timezone

| Overlay | Clock | Pine TZ |
|---------|--------|---------|
| HTF Fib / BTC H1 pullback | None (bar / HTF bar) | Chart / `request.security` TF |
| FX template | Broker server hours | `InpSessionTimezone` (`exchange` = `syminfo.timezone`) |
| US index scalp | ET / London / Tokyo with DST | `America/New_York`, `Europe/London`, `Asia/Tokyo` |
| BTC NY scalp | ET desk box | `America/New_York` |

## Universal overlay (one attach)

`UniversalOverlay.pine` is an **additional** chart attach. It does not replace or delete the five standalone files.

TradingView → Pine Editor → paste `UniversalOverlay.pine` → Add to chart → Settings → **Overlay family**:

| Family option | Standalone | Signal buffer | Notes |
|---------------|------------|---------------|-------|
| FX HTF Fib (ForexHtfPivotsFib) | `ForexHtfPivotsFib.pine` | **8** | Confirm-bar HTF pivots + golden-zone RSI. S/R CSV stays a stub. |
| FX template (ForexIndicatorTemplate) | `ForexIndicatorTemplate.pine` | **9** | Buffer 8 is the short arrow, not the signal. Spread gate stubbed. |
| US index scalp (UsIndexSessionScalp) | `UsIndexSessionScalp.pine` | **8** | IANA NY / London / Tokyo DST clocks |
| BTC H1 pullback (BtcTrendPullback) | `BtcTrendPullback.pine` | **7** | H4 completed-bar bias |
| BTC NY scalp (BtcNySessionScalp) | `BtcNySessionScalp.pine` | **8** | **SCREEN_FAIL / promote=no** banner + alerts when this family is selected |

Only the selected family's signal / VWAP / swing / ORB state runs each bar. `request.security` must stay registered (Pine limitation); unused families request the **chart** TF and a `na` expression (not H4/D1/H1 books, not pivots).

Session day-keys (`etKey`) are computed at global scope so `[1]` history works. Declaring them inside `if isUIS` can make `etKey[1]` na and reset VWAP every bar.

Family input titles are prefixed (`HTF InpEmaFast`, `UIS InpEmaFast`, …) so settings do not collide across groups.

The data-window plot named `signal` is the active family's iCustom series. The table and last-bar label show family code + buffer index (`HTFFIB/UIS/BNS=8`, `BTP=7`, `FXIT=9`). Unused visual series stay `na` (`display=` is a Pine const and cannot flip per family). The panel is created only when `InpShowPanel` is on.

GoldSessionScalp / OilSessionScalp are not options. Do not invent them.

## How to load (standalone)

TradingView → Pine Editor → paste a `.pine` file → Add to chart. These files are not compiled by MetaEditor and are not copied by `scripts/18-install-forex-indicator.sh`. Merge ≠ deploy. Not a live host.
