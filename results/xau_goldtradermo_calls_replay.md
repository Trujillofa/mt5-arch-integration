# GOLDTRADERMO call tape

**Outcome:** NO_NEW_FAMILY

**promote / live_go / PAPER_GO:** no / false / no

**family_id:** none. No charter. No develop screen. No second tune.

## What was counted

Text in the Telegram export was split into kept calls, excluded malformed prices, and everything else. A kept call has a side, an entry zone, at least one TP, and one SL, and every price in that message shares a scale and sits on the correct side of the zone. A price that cannot be reconciled is excluded and left as written.

Marketing replies are not calls. The export contains 1706 messages that say TP HIT or ALL TP Done. That count is the channel's advertisement. It is not the win count. Scored exits below were read off bar highs and lows.

| Count | Value |
| --- | ---: |
| parsed_total | 519 |
| parsed_calls | 503 |
| excluded_malformed | 16 |
| scored | 137 |
| unresolved | 366 |
| tp_hit_messages (not wins) | 1706 |
| scored_exits_from_bars | 137 |

Identity: excluded_malformed + scored + unresolved = parsed_total (16 + 137 + 366 = 519). parsed_calls = scored + unresolved (503 = 137 + 366).

Excluded reasons: digit_length=3, side_geometry=12, zone_arity=1.

Fill reasons: no_bar_after_call=118, same_bar_entry_and_exit=201, same_bar_sl_and_tp=47, sl=29, tp=108.

## Clock

Export titles are offset UTC-05:00. The price file `xauusd_data.csv` stamps M15 bars in UTC (100000 bars, 2022-05-17 09:15:00 through 2026-08-07 23:45:00). `bar_time` is the export instant converted to UTC. The bar that contains the call is not used. The first eligible bar is the next open after that instant.

## Fill convention

Entry is the first touch of the zone on an eligible bar. Full size is 1.0 lot, contract size 100. The position leaves at the nearest stated TP or the SL, whichever a later bar trades by itself. A bar that trades both stays unresolved. The fill bar is not an exit: if it also reaches the SL or the nearest TP, the call stays unresolved, because one OHLC bar cannot order the touch against the fill. No bar after the call, no touch of the zone, or neither level before the file ends: unresolved.

Cost is the entry bar's spread in points when that spread is positive, plus the cost book slippage 0.0 points and commission 0.0 per lot per side (`results/xau_research_costs.json`). When the bar has no positive spread, the charge uses the recorded assumption of 18.0 points, the median of the positive M15 spreads on this file. Round trip matches the research book: one spread, slippage on both fills, commission per lot per side.

## Signature of the messages

These figures describe the kept calls. They were not used to choose a rule or a knob.

* Time of day is the export clock UTC-05:00. Calls fall in 17 distinct hours. Counts by hour: 00:41, 01:35, 02:22, 03:30, 04:31, 05:33, 06:36, 07:38, 08:33, 09:20, 10:8, 11:3, 19:9, 20:27, 21:55, 22:48, 23:34.
* Side mix: buy 261, sell 242.
* Zone width in price units (high minus low): n=503, median=4, min=0, max=12.
* Stop distance beyond the zone: n=503, median=11, min=2, max=116.
* Distance from the zone to the nearest TP: n=503, median=4, min=2, max=11.
* Spacing between consecutive stated TPs: n=1509, median=4, min=1, max=96.
* Messages that name an indicator word: 0. Messages that name a session word: 0. Messages that name an exogenous series: 0.
* Bar time before 2026-01-01 00:00:00 UTC: 38. On or after that instant: 465.

The messages state a zone, a stop, and a TP ladder. They do not state an indicator rule.

## Closed-shape verdict

Matched shapes: intraday_own_price, session_books_closed_not_restated.

- Kept calls are an XAUUSD entry zone, a stop, and a TP ladder on the instrument's own price. docs/research/XAU-THESIS-PASS-2026-10-03.md already closes intraday own-price, including an indicator on XAUUSD itself.
- results/xau_loop_status.md closes session timing, Asia-box, and London sweep/fade (xau_gold_session_study SCREEN_FAIL, plus server_hour_window_flat, tod_london_ny_flat, and asia_box_london_sweep_fade_flat). The call text does not state a session rule. The hour-of-day counts are a description of the export clock, not a new occupancy.
- 465 of 503 kept calls have bar time on or after 2026-01-01 UTC. That window is the sealed holdout and is not a selection set. A knob chosen from those calls is forbidden.
- The 38 calls before the holdout use the same zone, stop, and TP template. They are not a different occupancy, so they do not open a family.

**NO_NEW_FAMILY.** promote / live_go / PAPER_GO stay no / false / no. Holdout dates were not used to pick or keep a family. `strategy_params.json` was not rewritten.
