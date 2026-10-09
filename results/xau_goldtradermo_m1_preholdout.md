# GOLDTRADERMO pre-holdout calls on M1

**Outcome:** NO_NEW_FAMILY

**promote / live_go / PAPER_GO:** no / false / no

This note rescores the kept calls whose bar time is before the sealed holdout, on M1, with the same fill rule as the M15 replay. It does not open a family, choose a knob, or read the later calls as a selection set.

## Who was rescored

Pre-holdout calls: 38. Post-holdout calls left unread: 466.

On M15, 16 of these calls had an ordered exit and 22 stayed unresolved because one 15-minute bar contained the fill and a level, or both the stop and the nearest TP.

On M1, 34 have an ordered exit and 4 stay unresolved. Entries on or after 2026-01-01 UTC: 1. Exits on or after that instant: 0. A fill after the holdout is the later life of a call placed before it. It was not used to choose a rule.

## Clock

The M1 file is official MT5 `get_chart_history` for Vantage XAUUSD. Its meta records trade-server offset 3.0h at 2026-09-24T20:44:48+00:00. That offset was not applied.

Offset 0 reproduces the UTC M15 tape: 16036 bars with at least 14 M1 rows inside the bucket, 16036 exact OHLC matches, window 2025-12-01 00:00:00 through 2026-08-08 00:00:00. A disagreement aborts the rescore before any fill.

## What the finer bar changed

| Transition | Calls |
| --- | ---: |
| m15_sl_unchanged | 2 |
| m15_tp_unchanged | 14 |
| unresolved_stays_unresolved | 4 |
| unresolved_to_sl | 1 |
| unresolved_to_tp | 17 |

M1 reasons: same_bar_entry_and_exit=3, same_bar_sl_and_tp=1, sl=3, tp=31.

## Money on the M1-ordered trades

Ordered on M1: 34. Net with the entry still before 2026-01-01: 12,844.00. Net with the entry on or after that instant: 0.00 across 0 ordered calls. Size is 1.0 lot after the entry minute's spread. The M1 spread field is the minimum tick spread inside that minute. Unresolved calls are absent from both nets.

This net describes the channel's already-stated calls. It is not a develop profit factor and it did not keep a family.

## Each pre-holdout call

| Export time | Message | Side | Zone | Stop | Nearest TP | M15 | M1 | M1 entry UTC | M1 exit UTC | M1 PnL |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | ---: |
| 2025-12-05 10:32:19 | message9206 | buy | 4241/4245 | 4230 | 4248 | tp | tp | 2025-12-05 16:47:00 | 2025-12-05 17:23:00 | 682.00 |
| 2025-12-10 04:03:58 | message9220 | sell | 4198/4200 | 4219 | 4194 | tp | tp | 2025-12-10 10:44:00 | 2025-12-10 11:46:00 | 582.00 |
| 2025-12-11 07:55:46 | message9227 | sell | 4218/4220 | 4228 | 4215 | same_bar_entry_and_exit | tp | 2025-12-11 12:56:00 | 2025-12-11 13:14:00 | 315.00 |
| 2025-12-11 20:42:11 | message9236 | buy | 4264/4266 | 4253 | 4270 | same_bar_entry_and_exit | tp | 2025-12-12 03:28:00 | 2025-12-12 03:44:00 | 382.00 |
| 2025-12-12 01:44:15 | message9251 | buy | 4278/4280 | 4270 | 4284 | tp | tp | 2025-12-12 07:35:00 | 2025-12-12 09:06:00 | 582.00 |
| 2025-12-12 03:23:01 | message9259 | buy | 4288/4292 | 4280 | 4295 | tp | tp | 2025-12-12 09:10:00 | 2025-12-12 10:12:00 | 682.00 |
| 2025-12-12 04:34:06 | message9270 | buy | 4208/4208 | 4198 | 4212 | same_bar_sl_and_tp | same_bar_sl_and_tp | 2026-03-23 09:43:00 |  |  |
| 2025-12-12 10:22:33 | message9278 | sell | 4325/4326 | 4336 | 4321 | same_bar_sl_and_tp | tp | 2025-12-12 17:19:00 | 2025-12-12 17:20:00 | 482.00 |
| 2025-12-14 20:36:03 | message9286 | buy | 4312/4315 | 4306 | 4318 | same_bar_entry_and_exit | tp | 2025-12-15 03:02:00 | 2025-12-15 03:35:00 | 582.00 |
| 2025-12-14 23:41:27 | message9296 | buy | 4320/4323 | 4312 | 4326 | same_bar_entry_and_exit | tp | 2025-12-15 05:14:00 | 2025-12-15 05:32:00 | 282.00 |
| 2025-12-15 07:18:23 | message9306 | buy | 4340/4342 | 4331 | 4345 | tp | tp | 2025-12-15 12:30:00 | 2025-12-15 14:01:00 | 282.00 |
| 2025-12-15 11:10:39 | message9311 | sell | 4307/4310 | 4320 | 4303 | same_bar_entry_and_exit | tp | 2025-12-15 18:04:00 | 2025-12-15 18:06:00 | 682.00 |
| 2025-12-15 22:37:43 | message9320 | sell | 4287/4290 | 4298 | 4284 | same_bar_entry_and_exit | tp | 2025-12-16 04:57:00 | 2025-12-16 05:11:00 | 582.00 |
| 2025-12-16 04:28:34 | message9327 | buy | 4278/4281 | 4270 | 4284 | same_bar_entry_and_exit | tp | 2025-12-16 09:29:00 | 2025-12-16 09:33:00 | 282.00 |
| 2025-12-16 21:41:53 | message9339 | sell | 4320/4324 | 4335 | 4316 | same_bar_entry_and_exit | tp | 2025-12-17 03:12:00 | 2025-12-17 03:20:00 | 382.00 |
| 2025-12-17 07:59:34 | message9351 | buy | 4312/4315 | 4300 | 4319 | tp | tp | 2025-12-17 14:13:00 | 2025-12-17 14:18:00 | 382.00 |
| 2025-12-17 22:21:07 | message9361 | buy | 4332/4335 | 4320 | 4340 | sl | sl | 2025-12-18 04:00:00 | 2025-12-18 14:28:00 | -1,218.00 |
| 2025-12-18 02:24:26 | message9367 | sell | 4334/4336 | 4345 | 4330 | tp | tp | 2025-12-18 07:25:00 | 2025-12-18 10:02:00 | 582.00 |
| 2025-12-18 21:54:39 | message9379 | buy | 4314/4316 | 4306 | 4320 | same_bar_entry_and_exit | tp | 2025-12-19 03:25:00 | 2025-12-19 03:48:00 | 382.00 |
| 2025-12-19 03:54:25 | message9392 | sell | 4328/4330 | 4338 | 4324 | same_bar_entry_and_exit | tp | 2025-12-19 09:13:00 | 2025-12-19 09:22:00 | 382.00 |
| 2025-12-19 10:37:40 | message9400 | sell | 4343/4345 | 4354 | 4339 | same_bar_entry_and_exit | tp | 2025-12-19 17:06:00 | 2025-12-19 17:26:00 | 382.00 |
| 2025-12-21 21:31:33 | message9405 | sell | 4384/4384 | 4397 | 4380 | same_bar_entry_and_exit | tp | 2025-12-22 03:47:00 | 2025-12-22 04:07:00 | 381.00 |
| 2025-12-22 00:01:32 | message9413 | buy | 4394/4396 | 4384 | 4400 | tp | tp | 2025-12-22 05:49:00 | 2025-12-22 06:51:00 | 581.00 |
| 2025-12-22 03:43:09 | message9423 | sell | 4410/4412 | 4418 | 4406 | same_bar_entry_and_exit | sl | 2025-12-22 08:45:00 | 2025-12-22 08:58:00 | -819.00 |
| 2025-12-22 11:49:30 | message9427 | buy | 4430/4434 | 4420 | 4438 | tp | tp | 2025-12-22 17:45:00 | 2025-12-22 18:14:00 | 781.00 |
| 2025-12-23 03:58:30 | message9439 | buy | 4484/4487 | 4473 | 4491 | tp | tp | 2025-12-23 09:18:00 | 2025-12-23 10:39:00 | 681.00 |
| 2025-12-24 08:33:58 | message9450 | buy | 4476/4480 | 4469 | 4484 | same_bar_entry_and_exit | same_bar_entry_and_exit | 2025-12-24 15:19:00 |  |  |
| 2025-12-24 09:48:59 | message9456 | sell | 4480/4482 | 4497 | 4476 | tp | tp | 2025-12-24 15:12:00 | 2025-12-24 15:20:00 | 581.00 |
| 2025-12-26 00:22:52 | message9468 | sell | 4510/4513 | 4521 | 4506 | same_bar_entry_and_exit | tp | 2025-12-26 05:23:00 | 2025-12-26 05:28:00 | 518.00 |
| 2025-12-26 01:52:04 | message9475 | buy | 4508/4510 | 4493 | 4514 | tp | tp | 2025-12-26 06:53:00 | 2025-12-26 07:31:00 | 381.00 |
| 2025-12-28 20:52:31 | message9489 | buy | 4499/4503 | 4484 | 4507 | same_bar_sl_and_tp | same_bar_entry_and_exit | 2025-12-29 02:22:00 |  |  |
| 2025-12-29 07:25:22 | message9503 | sell | 4455/4458 | 4473 | 4450 | tp | tp | 2025-12-29 12:31:00 | 2025-12-29 13:39:00 | 781.00 |
| 2025-12-29 21:21:41 | message9517 | sell | 4356/4358 | 4373 | 4351 | same_bar_entry_and_exit | tp | 2025-12-30 03:53:00 | 2025-12-30 04:35:00 | 481.00 |
| 2025-12-30 03:32:18 | message9524 | sell | 4358/4360 | 4377 | 4354 | sl | sl | 2025-12-30 08:45:00 | 2025-12-30 09:44:00 | -1,719.00 |
| 2025-12-30 06:45:04 | message9529 | buy | 4380/4383 | 4368 | 4388 | tp | tp | 2025-12-30 12:26:00 | 2025-12-30 12:30:00 | 781.00 |
| 2025-12-31 00:44:59 | message9544 | buy | 4322/4322 | 4310 | 4326 | same_bar_entry_and_exit | same_bar_entry_and_exit | 2025-12-31 07:40:00 |  |  |
| 2025-12-31 00:57:27 | message9549 | sell | 4290/4294 | 4318 | 4284 | same_bar_sl_and_tp | tp | 2025-12-31 07:53:00 | 2025-12-31 07:54:00 | 981.00 |
| 2025-12-31 08:58:14 | message9559 | buy | 4340/4344 | 4324 | 4348 | same_bar_entry_and_exit | tp | 2025-12-31 15:46:00 | 2025-12-31 15:58:00 | 781.00 |

## Why this is still not a family

M1 orders some paths that one M15 bar could not. The messages are still a zone, a stop, and a TP ladder on XAUUSD, with no indicator, session, or outside series named. That shape is already closed. The other calls in the export sit on or after 2026-01-01 UTC and were not used here.

**NO_NEW_FAMILY.** promote / live_go / PAPER_GO stay no / false / no.
