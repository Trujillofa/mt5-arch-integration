# Grill — `btc_h1_range_vol_breakout_v1` (Path 1b.2)

Frozen **before** any develop grid. Not a retune of `btc_h1_trend_pullback_v1`.

## Proposal

BTCUSD has no session close or gap. Trade a **closed-bar H1 close-through** of a prior-N high/low **only when** the last completed bar is an expansion after a measured squeeze. No H4 EMA stack, no H1 EMA/RSI/MACD reclaim, no sweep labels.

## Decisions (adversarial)

| Probe | Decision |
|-------|----------|
| v1 minus EMA? | **No.** v1 was H4 EMA50/200 permission + H1 RSI/MACD reclaim. This trigger is prior-N range + squeeze→expand. Different permission, different entry. |
| XAU Donchian recycle? | **No.** `KILL_DONCHIAN_LINE` was turtle/channel-follow on gold, no expansion gate. This family requires squeeze at *i−1* and TR expansion on *i*. Same helper name ≠ same family. Do not import XAU Donchian modules. |
| Liquidity sweep? | **Rejected.** No unverified sweep tags. Close-through only. A wick beyond the prior range that closes back inside is **not** a signal. |
| Range known when? | `donchian_prior`: window `i−n .. i−1`. Bar *i* is never inside the range. |
| Squeeze / expand causality? | Squeeze = `ATR14[i−1] / ATR50[i−1] ≤ squeeze_max`. Expand = `TR[i] / ATR14[i−1] ≥ expand_min`. ATR[*i*] includes TR[*i*] — **do not** use it as the squeeze baseline. |
| Why not NR7-on-*i*? | Requiring the breakout bar itself to be the narrowest bar contradicts expansion. Compression is prior; expansion is this close. |
| H4 / EMA / RSI / MACD? | **Off.** Thesis does not need H4. Loading H4 for “bias” would re-open the v1 starve. |
| Long-only? | **No.** v1 long-only printed 0 holdout trades because the H4 stack never flipped. Both sides frozen on so 2026 can fire. |
| Holdout date? | Same pin as v1 / `xau_holdout_lock.json`: select `signal_utc_date < 2026-01-01`. Not moved after seeing v1’s 2026 starve. |
| Book / 1%/20%? | Keep v1 book. 1%/20% is **not** a BTC gate at 0.01 lot. |
| Grid? | 16 = range_n × squeeze_max × expand_min × sl_atr. Ceiling 16. Do not retune after peek. |
| Pivots / Fib? | Not used. Do not import `htf_fib_core`. |
| Timescale? | **Not this task.** Leftover only if this screen also misses. |

## What would falsify

1. Develop-eligible configs = 0 after the frozen book (n≥40 and NP>0) → starved; do not loosen squeeze/expand.
2. Any eligible develop passer fails the soft gate on **develop** → SCREEN_FAIL; do not peek-tune.
3. Holdout used for selection → discard.
4. Forming last H1, or range/squeeze that includes bar *i*, leaks → causality fail.
5. **0 holdout trades** again (2026 did not fire) → mechanism starved, same class of fail as v1’s EMA gate.
6. Develop soft-pass **and** holdout PF<1 or NP≤0 → no edge out of sample.
7. Median trade-day still negative with no economic size → diagnostic fail (not a 1% gate).
8. Costs omitted / US100 10 pt slip / lots 1.0 → discard.

## Acceptance

Lock + tests (book tamper, holdout not in rank, range-known-at-close, squeeze uses *i−1*, no forming-bar signal, no EMA/H4) + bounded 16-config develop screen + results with **promote=false**. No `--live`. No XAU status edit. No Timescale.

## Next action

Freeze the lock, then implement and run the screen once.
