# Immutable family charters

**Layout:** `YYYY-MM-DD_<family_id>_vN.json`  
**Rule:** write-once. Never overwrite. Bump `vN` or date for a new freeze.  
**Dispositions:** append-only `../xau_charter_disposition_registry.jsonl` keyed by charter SHA — never edit freezes for status.

## Historical (do not overwrite)

| Path | Family | Note |
|------|--------|------|
| `../xau_next_design_charter.json` | `prior_day_high_break` | 2026-08-08 freeze; **KILL** under prior protocol. |

## Protocol freezes (2026-08-10+)

| Path | Family | Registry disposition |
|------|--------|----------------------|
| `2026-08-10_tod_london_ny_flat_v1.json` | `tod_london_ny_flat` | PROTOCOL_NULL_INVALID (SHA `e7cd953f…`) · r1 not burned |
| `2026-08-10_server_hour_window_flat_v1.json` | `server_hour_window_flat` | SUPERSEDED (SHA `6b5811ee…`) |
| `2026-08-10_server_hour_window_flat_v2.json` | `server_hour_window_flat` | **SCREEN_FAIL** ZERO_PRIMARY_PASSERS (SHA `26ff7532…`) · r1 **not** burned |

## 2026-08-20 freeze (design only)

| Path | Family | Note |
|------|--------|------|
| `2026-08-20_multi_day_variance_expansion_flat_v1.json` | `multi_day_variance_expansion_flat` | **FROZEN** · fixtures implemented · no develop peek · `AWAIT_REVIEW_THEN_DEVELOP_SCREEN` |

## Next family (when ready)

1. **New `family_id`** — do not reuse/rename server-hour or TOD rules.  
2. Freeze under this directory **before** inspecting its real grid.  
3. Sealed charters must be git-tracked and match `HEAD` blob.  
4. Run 999-trial null **only if** the real grid has ≥1 primary passer (else SCREEN_FAIL without nulls).

```bash
# Example shape only — freeze a NEW family first
python3 scripts/xau_sealed_family_cycle.py \
  --charter results/xau_charters/YYYY-MM-DD_<new_family>_v1.json \
  --family <new_family> \
  --run-id r1
```

Do **not** run sealed r1 on any SCREEN_FAIL / SUPERSEDED / PROTOCOL_NULL_INVALID SHA.
