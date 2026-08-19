# Next search pivot after US100 session-scalp

| Field | Value |
|-------|--------|
| **Date** | 2026-08-19 |
| **Trigger** | Eight US100 holdout blocks failed a 20-point RT / $10k / 1-lot / 1% median trade-day book |
| **Picked** | **Path 1b — BTCUSD H1 structural pullback** |
| **search_id** | `btc_h1_trend_pullback_v1` |
| **Lock** | `results/btc_h1_trend_pullback_v1_lock.json` |
| **promote / live_go** | **no / false** |
| **XAU status** | `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` — **not edited** |

US100 facts stay frozen. This is not a US100 continuation and not XAU Phase E.

---

## Grill (three paths)

### Path 1a — XAUUSD new thesis (London–NY displacement / `ForexHtfPivotsFib` buf 8)

| Probe | Finding |
|-------|---------|
| Status file | `next_step = RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` after Phase E `exog_london_fx_cosign_xau_follow_flat` SCREEN_FAIL |
| Sealed/failed | bb_rsi, Donchian, prior_day, TOD, server_hour, early_range, day_open, joint fade, exog follow — all closed |
| New thesis on disk? | No authorized family_id that is not a recycle |
| Displacement/Fib | Existing XAU pipeline + HTF Fib is a **dead-family neighborhood**, not a new clock/mechanism |

**Reject.** Idle means idle. A London–NY displacement screen would recycle sealed grammar (session clock, fib/pivots, FX cosign leftovers) without a genuinely new `family_id`. Default: do not edit `xau_loop_status.md`.

**Would have picked it if:** a written thesis with a new `family_id`, freeze-before-peek charter, and an explicit “not a sealed family” argument that survived this grill.

### Path 1b — BTCUSD H1 structural pullback (`BtcTrendPullback` buf 7)

| Probe | Finding |
|-------|---------|
| Indicator | `mql5/Indicators/BtcTrendPullback.mq5` v1.10 + `docs/research/BTC-INDICATOR-DESIGN.md` already on main |
| Prior screen | **None.** No BTC lock, no BTC CSV in `results/`, no freeze-before-peek holdout |
| Data | FP `BTCUSD` native `H1.hc` / `H4.hc` (2021-12 → 2026-08, ~29k H1). Offline `read_mt5_hc`. Does not kill `terminal64` |
| Specs (bridge `symbols.json`, read-only) | point **0.01**, contract **1.0**, digits **2**, tick_value **0.01**, min_lot **0.01** |
| Book honesty | **Must not** copy US100 $10k / 1 lot / 10 pt. 1 lot BTC ≈ $65k notional; live FP book is ~$2.6k and already traded **0.01**. 10 pt slip = $0.001 on 0.01 lot — rounding error vs H1 median spread **1251 pt (~$12.51 / 1 lot)** |
| Charter | Stays on Wine MT5 + offline Python. No `src/mt5_arch` import. No `OrderSend` |

**Pick.** New `search_id` on current stack. Indicator grammar exists; data exists; no prior peek.

**Falsify this pick (before/during the screen):**

1. Develop-eligible configs = 0 after the frozen book (n≥40 and NP>0) → family starved or dead; do not retune.
2. Any eligible develop passer fails the frozen soft gate on **develop** (PF≥1.1, NP>0, DD≤25%) → SCREEN_FAIL; do not peek-tune.
3. Holdout used for selection → protocol breach; discard the run.
4. Forming H4 or forming last H1 leaks into signals → causality fail; do not score.
5. Costs omitted or US100 10 pt slip reused → unfalsifiable / wrong book; discard.
6. 1%/20% claimed on a 0.01-lot book → structural lie (a 1% day on $10k is $100 ≈ a **$10,000** BTC move at 0.01 lot).

### Path 2 — Timescale true CVD

| Probe | Finding |
|-------|---------|
| In this repo | **No** Timescale, no compose, no tick schema. US100 v4–v8 locks: “charter excludes; no aggressor-tick store” |
| Tick folders | Wine prefixes have `ticks/BTCUSD` and `ticks/US100` — raw MT5 tick caches, **not** a research store |
| First increment | Would be design + lock + sample prototype, not a screen. Infra-heavy vs an unscreened BTC thesis |

**Defer.** Right architecture for *true* NY-open CVD later. Not the next executable workflow while BTC H1 pullback has never been frozen.

**Would have picked it if:** no BTC/XAU-new-thesis path, **and** a real first increment (schema + ingest plan + lock + local sample) was doable without standing up production.

### Path 3 — cTrader pivot for US100

| Probe | Finding |
|-------|---------|
| This repo | Wine MT5 + offline research. No cTrader research lane |
| Skills | `trading-backtest-validator` / `trading-strategy-developer` target `/home/yderf/ctrader-trading-agent` |
| Charter | Option B dual-layer. Building a cTrader bot here is out of charter |

**Reject.** Liquidity/spread comparison on cTrader is a **different repo**. Honest note only.

---

## Hardened proposal (picked)

Execute `btc_h1_trend_pullback_v1`: Python port of `BtcTrendPullback` (H4 completed EMA stack + H1 closed-bar reclaim), freeze-before-peek lock, FP native H1/H4 via `read_mt5_hc`, **actual** BTC book (0.01 lot, 250 pt slip/side, 4000 pt spread cap), select `signal_utc < 2026-01-01`, holdout sealed. Soft gates are XAU-like (n/PF/NP/DD), **not** the US100 1%/20% index-book goals. promote=no.

**Acceptance:** lock + tests (split / costs / lock tamper / no forming-bar leak) + bounded 16-config develop screen + results note. No live-go. No XAU status edit. No Timescale. No cTrader bot.

---

## Executed (2026-08-19)

Screen ran. `results/btc_h1_trend_pullback_v1.md`. Develop: 8 eligible, 5 soft (best PF 1.32, n=56, NP +$115, median day **−0.020%**). Holdout soft **0 / 16**. Long-only winner had **0** 2026 signals (3928 H1 bars exist). promote=no. Do not retune the 16.

---

## Path 1b.2 — new BTC mechanism, no EMA (2026-08-19)

| Field | Value |
|-------|--------|
| **Picked** | **`btc_h1_range_vol_breakout_v1`** after v1’s 2026 EMA starve |
| **Lock / grill** | `results/btc_h1_range_vol_breakout_v1_lock.json` · `results/btc_h1_range_vol_breakout_v1_grill.md` (frozen before grid) |
| **Thesis** | Closed-bar H1 **close-through** of prior-N high/low only after ATR14/ATR50 squeeze at *i−1* and TR[*i*] expansion. Both sides. **No H4, no EMA/RSI/MACD.** |
| **Not** | v1-minus-EMA · XAU Donchian turtle · liquidity-sweep labels · Timescale |
| **Book / split** | Same as v1: $10k / 0.01 lot / 250 pt slip / select `< 2026-01-01` |
| **promote / live_go** | **no / false** |
| **XAU status** | unchanged — **not edited** |

### Executed

Screen: `results/btc_h1_range_vol_breakout_v1.md`. Develop eligible **4** · soft **1** (best PF **1.11**, n=293, NP +$144, median day **−0.023%**). That row’s holdout: n=**37** (16 long / 21 short), PF 1.17, NP +$32 — **n<40**, not a holdout soft. Holdout n>0 on **16/16** (2026 fired). Any-row holdout soft = 1 is a develop **fail** (row 4); do not select it. promote=no. Do not retune the 16.

**vs v1:** the EMA-starve falsifier did **not** repeat. The economic / holdout-n falsifier still holds.

**Leftover:** Timescale true CVD (infra). Do not start it from this screen. Do not reopen US100, sealed XAU, or v1’s 16.
