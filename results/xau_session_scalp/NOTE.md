# XAU session scalp — CLOSED / observe-only

**Disposition (2026-09-09):** **CLOSED**. M5 session-OR scalp is structurally
cost-killed on this tape. `GoldSessionScalp` is a chart overlay / research
artifact only. **promote=no · live_go=false · observe-only.**

Do not retune `xau_london_defined_r_be_flat_v1`. Do not chase 80% WR on
sub-15m XAU. Do not attach this indicator as a live entry host.
Terminal records below are intact. Status: `STATUS.md`.

---

# XAU session scalp — baseline vs adjusted

| Field | Value |
|-------|--------|
| Date | 2026-09-08 |
| Family (adjusted) | `xau_london_orb_overlap_vwap_ema_flat` |
| Family (baseline) | `ny_cash_orb_vwap_ema_flat` (unmodified index rules on gold) |
| Holdout | **2026-01-01** UTC — evaluation only |
| promote / live_go | **no / false** |
| XAU loop | untouched (`results/xau_loop_status.md` still RESEARCH_IDLE / promote=no) |

Not a claim of edge. Not a sealed XAU family. Do not write `strategy_params.json`.
Do not attach an order EA.

## Costs (both books)

| Knob | Value |
|------|-------|
| point_size | 0.01 (1 MT5 point = $0.01 of price) |
| contract_size | 100 |
| lots | 1.0 |
| commission | 0 (Standard STP shape) |
| slippage | **10 points / side** (unmeasured, explicit) |
| max spread | 40 points (fail-closed) |
| RT formula | `(spread_pts + 20) * 0.01 * 100` USD / lot + bar spread |

A 21-pt Vantage-like spread + 20 pt slip ≈ **$41** round-trip per lot.
FP M5 median spread on this cache is ~6 pt, so that tape **understates**
Vantage STP friction. Vantage M15 median spread is ~18 pt.

## Data

| Tape | Bars | Window | Role |
|------|-----:|--------|------|
| FP `XAUUSD.r` M5.hc | 100 190 | 2025-04-03 → 2026-09-01 UTC | **Primary** (true M5; server offset 0) |
| Vantage XAUUSD M15.hc | 100 064 | 2022-06-06 → 2026-08-28 UTC | Cost-matched transfer (not for selection) |
| Vantage XAUUSD M5.hc | 5 531 | 2026-08-07 → 2026-09-04 | Too short; entirely after holdout — unused |

`xauusd_data.csv` is H1 + M15 (Vantage spreads) and was not the primary
scalp tape. M1 Vantage cache starts 2026-05-27 (holdout only).

## Baseline — unmodified index rules on gold

NY cash 15m OR from 09:30 ET, entry `[09:45, 11:30)` ET, flatten **15:45 ET**,
no ATR SL/TP, one signal per ET date. Gold cost book.

### FP M5 (primary)

| Slice | n | WR | PF | Net (1 lot) | Avg |
|-------|--:|---:|---:|------------:|----:|
| Develop `< 2026-01-01` | 191 | 52.4% | **1.01** | +2 302 | +12 |
| Holdout | 168 | 47.0% | 1.23 | +62 057 | +369 |

### Vantage M15 (transfer)

| Slice | n | WR | PF | Net (1 lot) |
|-------|--:|---:|---:|------------:|
| Develop | 770 | 50.0% | 1.11 | +48 332 |
| Holdout | 140 | 51.4% | 1.40 | +81 929 |

Why this is not “index params work on gold”:

1. The hold is **hours**, not a scalp. 15:45 ET flatten rides the 2024–2026
   gold trend. Median MAE/MFE on the index US100 tape already showed this leak;
   here the leak is in the winner's direction on a bull tape.
2. Develop PF is ~1.0–1.1 after costs — not a cleared research gate.
3. Holdout is **evaluation only** and includes the 2026 melt-up. Do not select
   or promote from it.
4. The event clock is still US **cash** 09:30. Gold does not have that print.

## Adjusted — gold session boxes

London 30m OR, London VWAP, EMA 9/21, 0.10 ATR buffer, London `[OR end, 11:00)`
plus NY metals `[08:00, 11:00)` ET, 1.0/1.2 ATR SL/TP, flatten at the box end.
Same gold cost book. Primary candidate frozen in `lock.json` before metrics.

### FP M5 (primary)

| Slice | n | WR | PF | Net (1 lot) | Avg |
|-------|--:|---:|---:|------------:|----:|
| Develop | 381 | 43.0% | **0.82** | −13 157 | −35 |
| Holdout | 334 | 41.6% | 0.79 | −23 440 | −70 |

### Vantage M15 (transfer)

| Slice | n | WR | PF | Net (1 lot) |
|-------|--:|---:|---:|------------:|
| Develop | 1 684 | 45.5% | 0.83 | −49 285 |
| Holdout | 307 | 44.6% | 0.97 | −5 642 |

Develop-only sensitivity (FP M5; holdout **not** used):

| Candidate | n | PF | Net |
|-----------|--:|---:|----:|
| `london30_both_windows` (primary) | 381 | 0.82 | −13 157 |
| `london30_london_only` | 189 | 0.80 | −6 479 |
| `london15_london_only` | 193 | 0.74 | −9 300 |

The short-box scalp **loses after costs** on both tapes. That is the relevant
result for an overlay that claims to be a scalp. Alternates are worse or
equal on develop; they were not promoted onto the indicator.

## What changed vs the index overlay, and why

| Index | Gold |
|-------|------|
| NY cash 09:30 OR 15m | London 08:00 OR 30m |
| NY-cash VWAP | London-date VWAP |
| Entry `[09:45, 11:30)` ET only | London morning + NY metals 08:00–11:00 ET |
| Flatten 15:45 ET | Flatten 11:00 local to the box; ATR SL/TP |
| One per ET date | One per session box |
| OR buffer 0 | 0.10 ATR (London is a 23h continuation, not a cash discontinuity) |
| Index points / contract 1 | Gold points 0.01 / contract 100 |
| Spread cap 200 (US100) | Spread cap 40 |

## Indicator

`mql5/Indicators/GoldSessionScalp.mq5` + `mql5/Include/GoldSessionUtils.mqh`.
Signal buffer **8**. No `OrderSend`. Not a rename of `UsIndexSessionScalp`.

## Next steps (not done)

- Wine compile / attach on a live XAUUSD M5 chart (not run here).
- A Vantage M5 develop tape does not exist on this host; export one before
  claiming M5 + Vantage-STP jointly.
- Do not retune OR / EMA / windows on these CSVs. A new `family_id` would
  need freeze-before-peek.
- Standing XAU charter families stay closed. This track does not reopen them.


---

## Defined-R v1 — risk refactor (2026-09-08)

| Field | Value |
|-------|--------|
| Family | `xau_london_defined_r_be_flat_v1` (supersedes `xau_london_orb_overlap_vwap_ema_flat`) |
| Lock | `defined_r_v1_lock.json` — **frozen before** the 16-cell search |
| Score | eligible = select n≥40 and PF≥1.0 and payoff≥0.22; rank = **max WR on select**. If none: max select PF among n≥30 |
| Primary | `tpr1_be0_ts6` — 1.0 ATR SL, 1.0R TP, no BE, 6-bar time-stop |
| 80% WR + PF≥1 | **Miss.** Not achievable on this tape + cost model without breaking expectancy |
| promote / live_go | **no / false** |

### Autopsy of the prior ATR book (develop, FP M5)

n=381: SL 215 / TP 164 / same-bar 1 / flatten 1. Median hold **2 M5 bars**.
London and NY equally bad (~42–44% WR). Flatten almost never fires.
This is an SL/TP race on M5 noise, not a time leak.

### Frozen 16-cell Pareto — **select only** (`utc_date ≤ 2025-10-31`)

| Cell | n | WR | PF | Net $ | payoff | elig |
|------|--:|---:|---:|------:|-------:|:----:|
| tpr0.35_be0_ts0 | 168 | **69.6%** | 0.60 | −7 357 | 0.26 | no |
| tpr0.35_be0_ts6 | 168 | 69.6% | 0.60 | −7 357 | 0.26 | no |
| tpr0.5_be0_ts0 | 220 | 66.8% | 0.75 | −6 119 | 0.37 | no |
| tpr0.5_be0_ts6 | 220 | 65.9% | 0.73 | −6 446 | 0.38 | no |
| tpr0.7_be0_ts0 | 230 | 58.7% | 0.78 | −6 760 | 0.55 | no |
| tpr0.7_be0_ts6 | 230 | 58.3% | 0.78 | −6 726 | 0.56 | no |
| tpr1_be0_ts0 | 230 | 47.8% | 0.83 | −6 447 | 0.90 | no |
| **tpr1_be0_ts6** (honest book) | 230 | 47.8% | **0.83** | −5 886 | 0.91 | no |
| any `be_r=0.40` | 168–230 | 6–11% | ≤0.11 | −15k…−20k | 0.78–1.47 | no |

BE at 0.4R **destroys** WR: gold M5 often tags 0.4R then mean-reverts through entry.
Those scratches are losses after costs. Not used.

### Primary windows (evaluate confirm/holdout once; not used to pick)

| Slice | n | WR | PF | Net (1 lot) | 0.5% of $10k | median risk lots |
|-------|--:|---:|---:|------------:|-------------:|-----------------:|
| Select ≤2025-10-31 | 230 | 47.8% | 0.83 | −5 886 | −1 400 | 0.19 |
| Confirm Nov–Dec 2025 | 40 | 45.0% | 0.72 | −2 351 | −347 | 0.14 |
| Develop `< 2026-01-01` | 270 | 47.4% | 0.81 | −8 237 | −1 747 | 0.18 |
| Holdout ≥2026-01-01 | 226 | 44.2% | 0.78 | −14 126 | −1 550 | 0.11 |

Exits (select): TP 105 / SL 109 / time-stop 16. Every trade has a hard stop.

### Grill: why 80% WR + PF≥1 failed

At WR=80%, need `tp_r ≥ (c/S + 0.20) / 0.80`. With S≈$2.6 ATR and c≈$25,
that is `tp_r ≥ 0.37`. The 0.35R cell is the locked WR-trap: it prints the
**highest WR (69.6%)** and the **worst PF among no-BE cells (0.60)**.
Even that trap never reached 80%. Tighter TP than the frozen grid would
only deepen the trap; it was not searched after peeking.

A 15:45-ET hold (the index-on-gold baseline) can print PF≈1 by riding the
2025–26 gold trend. That is not a scalp and is not this overlay.

**Verdict:** 80% WR and PF≥1 after gold costs are incompatible on this
select tape under the frozen defined-R grid.

### Skills applied vs skipped

Applied (as principles; these skills are written for the cTrader agent):
strategy-developer, risk-troubleshoot, signal-analyzer, backtest-validator,
session-momentum, grill-me. Data-pipeline skipped — FP M5 / Vantage M15
already sufficient.

Skipped as **wrong product / not this repo:** trading-telegram-bot,
trading-deployment, trading-metrics-dashboard, trading-paper-monitoring,
prop-firm-compliance.

### Best current gold indicator in-repo?

`GoldSessionScalp` is the **only** gold-scalp overlay. `ForexHtfPivotsFib`
is the other gold *indicator*, but it is an H1/M15 swing-fib tool, not a
session scalp. Closed XAU script families (bb_rsi, donchian, …) are not
chart indicators. "Best current" ≠ profitable. This track stays
research-only / promote=no.
