# ADR 0001 — Kafka as an optional research signal bus

**Status:** accepted for research scaffolding only · **promote=no** · **live_go=false**  
**Date:** 2026-09-19  
**Does not place orders.** Merge ≠ host deploy. Does not enable Kafka on any live terminal.

Related: [CHARTER-RESEARCH-LAYER.md](../CHARTER-RESEARCH-LAYER.md),
[SEVEN-DESK.md](../SEVEN-DESK.md),
[ARCHITECTURE.md](../ARCHITECTURE.md),
[KAFKA-SIGNAL-BUS.md](../research/KAFKA-SIGNAL-BUS.md),
[research/kafka-signal-bus/README.md](../../research/kafka-signal-bus/README.md).

Article (producer-side reference only, not imported as production code):
[MetaTrader 5 as a Kafka Producer: Event-Bus Architecture for Multi-Terminal Signal Fan-Out](https://www.mql5.com/en/articles/24199).

---

## Decision

Apache Kafka may exist in this repo as an **optional signal / telemetry fan-out bus**
for research, dashboards, and paper EA experiments.

**Mt5ArchBridge file-bridge snapshots remain the operational source of truth**
for account, positions, orders, and Seven Desk. Kafka must not replace that path
and must not be dual-written in a way that lets a consumer treat Kafka as desk state.

This PR lands Phase A plus a Phase B **log-only** Python stub. It does **not**
port the article’s native MQL5 Produce protocol (varint, CRC32C, RecordBatch v2,
queued retries) as production code. That protocol is useful and unfinished if
ever added later; mark any such helpers experimental and keep them out of
`src/mt5_arch` and out of `scripts/18-install-forex-indicator.sh`.

---

## Why Kafka is interesting (and why it is not desk truth)

The article solves a **one-to-many distribution** problem: one terminal publishes
a signal once; many subscribers (dashboard, research logger, paper EA) consume
independently, including after they come online. That is the opposite shape of
the file bridge, which is a **local, authoritative snapshot** of one booked
terminal (account / positions / orders JSON under `MQL5/Files`).

| Path | Shape | Role in this repo |
|------|--------|-------------------|
| Mt5ArchBridge file bridge | one terminal → files → Python / Seven Desk | **Authoritative** for desk ops and order management |
| Kafka signal topic | one producer → broker → N consumers | **Optional fan-out** of research/paper *signals*, not positions |

Kafka is unsuitable as a replacement for operational account/position truth:
offsets can be replayed, consumers can be late or split-brain, and a signal is
not a fill. Seven Desk already has a fail-closed live path via
`desk_live_order_request.txt` and a stale `heartbeat.txt`. That must stay the
only order path.

---

## Recommended phases

| Phase | What | This PR |
|-------|------|---------|
| **A** | Versioned `SignalRecord` schema + local Kafka compose + paper-only publisher stub | **In** |
| **B** | Optional Python consumer that writes research logs / metrics only (stdout or file) | **Stub in** (file/JSONL dry-run; Kafka client is optional and off by default) |
| **C** | Any live path, funded-book attach, or order-capable consumer | **Out** — only with explicit human approval later. Not implied by merge. |

---

## Explicit non-goals (REJECT list)

Do **not** implement any of the following in this lane without a new, explicit
approval that names the book and the operator:

1. **Order consumers** — Kafka → `OrderSend` / cancel / modify / SLTP on any book.
2. **Seven Desk wiring** — no Kafka feed into positions, blotter, copy fan-out,
   `POST /api/wsf/order`, or `desk_live_order_request.txt`.
3. **Funded / prop Wine prefixes** — do not enable on
   `~/.mt5-wsf`, `~/.mt5-ftmo`, `~/.mt5-fundingpips`, `~/.mt5-fundednext`,
   `~/.mt5-alphacapital`, `~/.mt5-fortraders`, `~/.mt5-neomaa`, or any live
   `WINEPREFIX`.
4. **Replace or dual-write away from the file bridge** — `Mt5ArchBridge.mq5`
   must not depend on Kafka; snapshots stay authoritative.
5. **Auto-mirror / multi-terminal signal fan-out into funded accounts.**
   The article’s “mirror terminals trading correlated pairs” example is a
   **reject** for prop books.
6. **Host / OMARCHY deploy** — merge does not install compose, open ports, or
   change live launcher / systemd units.
7. **Secrets or real broker endpoints in tree** — placeholders only
   (`127.0.0.1`, `KAFKA_BOOTSTRAP_SERVERS`).
8. **Claim the article’s binary Produce implementation is production-ready.**

---

## Schema contract

Wire payload is JSON, versioned with `schema_version` (integer, currently `1`).
Canonical schema:
[`research/kafka-signal-bus/schema/signal_record.v1.json`](../../research/kafka-signal-bus/schema/signal_record.v1.json).

Required fields: `schema_version`, `symbol`, `side`, `timeframe`,
`strategy_id`, `terminal_id`, `ts`, `book_mode`.

Additive / optional (article-compatible): `signal_type`, `entry`, `sl`, `tp`,
`confidence`, `timestamp_ns`, `partition_key`. Extra properties are allowed so
v1 can grow without a bump; removing or retyping a required field requires v2.

`book_mode` is `paper` or `live`. Stubs treat only `paper` as loggable research
traffic. A structurally valid `live` record is **not** permission to act.

Recommended topic: `mt5.signals.paper.v1`.
Partition key (when present): `{symbol}_{timeframe}` so one instrument/timeframe
stays ordered on one partition — the article’s useful bit, without adopting its
EA.

---

## What was recommended vs deferred

**Recommended and in this PR**

- This ADR and the research how-to.
- Versioned JSON Schema + paper example.
- Localhost-only docker compose (optional UI profile).
- Stdlib schema verifier + paper stub (file/JSONL; optional Kafka client stays
  uninstalled and disabled).
- Paper-only MQL5 *contract* include (JSON field names, no sockets, no orders).
  Not copied by `scripts/18-install-forex-indicator.sh`.

**Deferred (not in this PR)**

- Native MQL5 Kafka Produce (varint, CRC32C, RecordBatch v2, Produce v7, retries).
- Metadata / leader discovery / consumer groups in MQL5.
- Any Python package dependency on `kafka-python` / `confluent-kafka`.
- Live topics, prop-prefix env files, Seven Desk consumers, order outbox.
- Phase C.

---

## Consequences

- `src/mt5_arch` does not import this lane.
- Research scripts stay offline: `python3 scripts/verify_kafka_signal_schema.py`
  and `python3 scripts/kafka_signal_bus_stub.py` (host Python; no new
  `pyproject.toml` deps).
- Standing XAU disposition is unchanged (`promote=no`, `live_go=false`).
- Reviewers should reject follow-ups that “just add” a live consumer or attach
  the stub EA to a funded chart.
