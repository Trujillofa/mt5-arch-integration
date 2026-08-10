# TOD London–NY flat v1 — disposition (registry)

**Charter file:** `results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json`  
**Charter SHA-256:** `e7cd953f998015bbc9aa5ae23ea7f35c45723f82736a273274f41102bac2f4cf`  
**Disposition:** `PROTOCOL_NULL_INVALID` / exploratory `SCREEN_FAIL`  
**r1 sealed run:** **NOT burned**

## Immutability

The charter JSON is **restored byte-for-byte** to its original freeze (commit `664a79c`).  
Invalidation is recorded **only** in the append-only registry:

`results/xau_charter_disposition_registry.jsonl`

keyed by `charter_sha256` — the charter file itself must not be edited for disposition.

## Why invalid

1. Original null method `day_block_shuffle` is statistically invalid for hour rules.
2. Server hour 13 is not established as London–NY wall-clock overlap.
3. Quick smoke: real soft passers = 0 ⇒ `p_n_passers = 1` for any n_null.

## Supersession

`server_hour_window_flat` + `within_day_return_rotate` (v2.2 normalized OHLC increments, k∈{0..m-1}).
