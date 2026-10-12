# XAU thesis pass — 2026-10-03

**Kind:** read-only keep/kill note.
**Standing next step:** `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS` (`results/xau_loop_status.md` head, 2026-09-24).
**promote / live_go / PAPER_GO:** no / false / no. This note does not change them.
**K_prior for a later family:** 25, from that same status block.
**Holdout:** `2026-01-01`. The holdout is not used for selection. No bar after that cut was read for this pass.
**Not in this note:** a new `family_id`, a charter, a develop profit factor, a screen, a null trial, or a freeze.

Catalog and blog profit factors are not evidence (`docs/ARTICLE-INTAKE.md`). None are repeated below.

## What would have to be new

`docs/research/BACKTEST-RECORD.md` (2026-08-21) states the class rule: intraday indicator-on-own-price is falsified under friction. A later idea has to change horizon or structure. The charter directory and the status head already close these shapes:

| Shape | Already closed in this tree |
| --- | --- |
| Session hour, opening range, day-open reclaim, Asia-box London sweep | `server_hour_window_flat`, `tod_london_ny_flat`, `early_server_range_break_flat`, `day_open_reclaim_flat`, `asia_box_london_sweep_fade_flat`, and `xau_gold_session_study` (timing / sweep / fade, `SCREEN_FAIL`) |
| Own-price trend, pivot pullback, Donchian, Bollinger, prior-day break | `xau_h4_pullback_weekly_long_only_v1` (H4 pivot reclaim with weekly EMA permission), plus the Donchian, `bb_rsi`, and `prior_day_high_break` kills in the status file |
| FX lead into XAU, log-spread fade, time-varying beta | `joint_london_open_cosign_fade_flat` v1–v4, `exog_london_fx_cosign_xau_follow_flat` v1–v4, `exog_eur_gbp_tvbeta_xau_long_or_flat_v1`, `xau_eur_logspread_ou_fade_v1`, `xau_xag_logspread_ou_fade_v1`, `eur_gbp_logspread_ou_fade_v1` |
| Vol-target always-long | `xau_garch_voltarget_always_long_v1`, `xau_gvz_voltarget_always_long_v1` |
| Scheduled macro event, long-only | `xau_fomc_h4_long_only_v1` |
| COT gold positioning fade | `xau_cot_gc_mm_fade_long_or_flat_v1` |
| Multi-day variance fade, Renko brick vehicles, AUDJPY carry | `multi_day_variance_expansion_flat`, `renko_event_clock_vendor`, `audjpy_carry_long_hold_v1` |

## Public posts read for this pass

Search extracts only, 2026-10-03, from `mql5.com` blogs and one calendar page. Full article HTML was not fetched. The entry rule was visible in the extract, which is enough to classify the shape.

| Source | Visible rule | Verdict |
| --- | --- | --- |
| [TrendCandleEA, M30 XAUUSD](https://www.mql5.com/en/blogs/post/775609) | M30 trend continuation after a pullback, fixed reward/risk or trail | **KILL.** Own-price intraday. |
| [Five XAUUSD time zones](https://www.mql5.com/en/blogs/post/770149) | GMT windows (Asia pre-London, London open, pre-New York, New York overlap, New York close) plus an overnight-range filter | **KILL.** Session windows. Same class as `xau_gold_session_study` and the server-hour books. |
| [H4 as the trend-following sweet spot](https://www.mql5.com/en/blogs/post/770260) | H4 entries only when daily EMA(50) and EMA(200) agree | **KILL.** Own-price H4 trend with a higher-timeframe permission. Same class as `xau_h4_pullback_weekly_long_only_v1`. |
| [MA pierce, gold and oil](https://www.mql5.com/en/blogs/post/773744) | Uptrend, bar pierces a slow average, buy-stop at the bar high | **KILL.** Own-price bar pattern. |
| [EMA cross, HMA, Parabolic SAR briefs](https://www.mql5.com/en/blogs/post/775441) and the same author's 7–9 Sep 2026 posts | 20/50/200 EMA or HMA or SAR dot, sometimes with "yields falling" as a sentence in front of the cross | **KILL.** The order is still an own-price cross. The yield sentence is not a dated series, a lag, or a flat time. |
| [Golden Ideal Pro growth post](https://www.mql5.com/en/blogs/post/767891) | Catalog EA, no stated entry | **KILL.** No occupancy to freeze. Catalog growth is not evidence. |
| [CFTC gold non-commercial net positions](https://www.mql5.com/en/economic-calendar/united-states/cftc-gold-non-commercial-net-positions) | Weekly net-position prints | **KILL.** Same object as `xau_cot_gc_mm_fade_long_or_flat_v1`, which is `SCREEN_FAIL`. |
| [Central-bank tonne commentary](https://www.mql5.com/en/blogs/post/774507) and the tonne sentences inside the EMA briefs | "Central banks bought N tonnes" as a narrative | **KILL as a rule.** No release timestamp, no lag, no side, no flat. It is not an occupancy. |

## Result

**NO_KEEP.**

Nothing in this pass is a new horizon or a new structure. The posts that name an entry are own-price or session rules already closed in this tree. The macro sentences do not name a testable occupancy, so they are not a candidate either.

This note does not authorize a charter. A later freeze still needs one named occupancy that is absent from the table above, in its own commit, with no develop metric in that commit.
