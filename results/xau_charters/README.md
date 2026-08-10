# Immutable family charters

**Layout:** `YYYY-MM-DD_<family_id>_vN.json`  
**Rule:** write-once. Never overwrite. Bump `vN` or date for a new freeze.

## Historical (do not overwrite)

| Path | Family | Note |
|------|--------|------|
| `../xau_next_design_charter.json` | `prior_day_high_break` | 2026-08-08 freeze; **KILL** under prior protocol. Left in place as historical record — new charters go **here** only. |

## Protocol v2 (2026-08-10+)

| Path | Family | Status |
|------|--------|--------|
| `2026-08-10_tod_london_ny_flat_v1.json` | `tod_london_ny_flat` | Freeze **immutable** (SHA `e7cd953f…`). Disposition in **registry only** → PROTOCOL_NULL_INVALID. r1 not burned. |
| `2026-08-10_server_hour_window_flat_v1.json` | `server_hour_window_flat` | FROZEN server-hour thesis; null=`within_day_return_rotate` **v2.2**; n_null=999. Sealed run optional. |

Append-only dispositions: `../xau_charter_disposition_registry.jsonl` (keyed by charter SHA).

Required fields: `gates` (classic+soft), `null.method` + `null.n_trials` (≥199; 999 for 0–1 knobs), `rule.intraday_flat` or swap handling, `protocol_version: 2`.

Sealed run:

```bash
python3 scripts/xau_sealed_family_cycle.py \
  --charter results/xau_charters/2026-08-10_tod_london_ny_flat_v1.json \
  --family tod_london_ny_flat \
  --run-id r1
```

Do **not** fold this cycle into PR #1 until that PR’s current scope is reviewed.
