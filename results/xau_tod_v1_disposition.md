# TOD London–NY flat v1 — disposition

**Date:** 2026-08-10  
**Charter:** `results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json`  
**Disposition:** `PROTOCOL_NULL_INVALID` / exploratory `SCREEN_FAIL`  
**r1 sealed run:** **NOT burned** (correctly withheld)

## Why

1. **Null invalid:** `day_block_shuffle` pastes variable-length absolute-price day blocks onto fixed timestamps without rebasing. Real develop days have 5/19/20/21/23 bars; hour-13 opportunity counts and ATR paths are distorted. `day_bar_count_multiset` was tautological under fixed timestamps.
2. **Clock claim unproven:** Server hour 13 is not established as London–NY overlap (MT5 server strings tagged as UTC without conversion; hours 1..23 present, hour 0 absent).
3. **Quick smoke:** real soft passers = 0 while null passers ≥ 0 ⇒ `p_n_passers = 1` under add-one smoothing for any trial count — 999 trials cannot rescue.

## Supersession

Use `server_hour_window_flat` with `within_day_return_rotate` null (`results/xau_charters/2026-08-10_server_hour_window_flat_v1.json`). Do not revive `tod_london_ny_flat` under the invalid null.
