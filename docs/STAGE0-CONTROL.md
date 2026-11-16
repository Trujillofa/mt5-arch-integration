# Stage 0 control surface — entry inhibit switch

**Scope:** read-only switch that lets a coordinator stop **new entries** on the MT5
side. Exits (`close`, `cancel`, `modify`) are never gated. This is a circuit
breaker for new risk, not a position manager.

Related: issue #132, [ADR 0001](adr/0001-kafka-signal-bus.md) (Kafka is not this
path), [ARCHITECTURE.md](ARCHITECTURE.md).

## File contract

| Field | Type | Notes |
|-------|------|-------|
| `version` | integer | Schema version, currently `1` |
| `account_id` | string | Coordinator's account identifier (informational here) |
| `inhibited` | boolean | **Required.** `true` blocks entries; `false` allows |
| `operator` | string | Who set it |
| `reason` | string | Surfaced in the EA result JSON |
| `updated_at` | string | ISO-8601 timestamp from the coordinator |

Path: `MQL5/Files/mt5_arch/control.json`, with a `FILE_COMMON` fallback —
the same lookup shape as the other bridge snapshots.

**Ownership:** the coordinator writes this file (atomic replace / fcntl). The EA
**only reads** it and never writes `control.json` (in particular, it never
writes `inhibited=false`).

## Failure semantics

| State | Entries |
|-------|---------|
| File absent | **Allowed** (no switch deployed yet) |
| `inhibited=true` | **Blocked**, `reason`/`operator`/`updated_at` returned |
| `inhibited=false` | Allowed |
| File unreadable (empty read) | **Blocked** — `control.json unreadable` |
| File malformed / no boolean `inhibited` | **Blocked** — `control.json malformed` |

Blocked entries return a normal fail result with `stage: "control"` and
`message: "entries inhibited — …"`; the request is not retried and no order is
sent.

## When it is read

- **At EA startup** (`OnInit`, writer instance): logs `inhibited`, `reason`,
  `operator`, `updated_at`.
- **Before every entry** (`open`, and `scratch` because it opens first) in
  `DeskOrdProcessRequest`. The file is re-read every time, so a coordinator
  update takes effect on the next request — no restart.

## Not in this slice

- Prometheus gauges (equity, margin, open positions, exposure, control age,
  `feed_stale`).
- XAUUSD per-firm contract size.
- A `REDUCE`/`FLAT` actor in `DeskOrderBridge.mqh` (closing by ticket). That is
  the order path: it needs an F7 compile plus a live-terminal gate.

## Deploy note

MQL5 is compiled in MetaEditor (F7) and deployed per Wine prefix through
`./scripts/18-install-forex-indicator.sh`. CI only runs the static contract
tests in `tests/test_desk_control_gate.py`.
