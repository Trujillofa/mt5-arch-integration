# Kafka signal bus — research how-to

**Status:** research-only scaffolding · **promote=no** · **live_go=false**  
**Does not place orders.** Does not attach to a Wine terminal. Merge ≠ host deploy.

Policy and reject list: [ADR 0001](../adr/0001-kafka-signal-bus.md).  
Operator files: [research/kafka-signal-bus/README.md](../../research/kafka-signal-bus/README.md).

Mt5ArchBridge file-bridge JSON under `MQL5/Files` remains Seven Desk truth.
This lane is an optional paper/dev fan-out. Do not enable it on funded prefixes
(`~/.mt5-wsf`, `~/.mt5-ftmo`, `~/.mt5-fundingpips`, `~/.mt5-fundednext`,
`~/.mt5-alphacapital`, `~/.mt5-fortraders`, `~/.mt5-neomaa`).

## Schema validate (offline, no broker)

```bash
python3 scripts/verify_kafka_signal_schema.py
python3 scripts/verify_kafka_signal_schema.py research/kafka-signal-bus/schema/examples/signal_record.paper.v1.json
uv run pytest tests/test_kafka_signal_bus.py
```

## Local compose (optional; laptop / lab only)

```bash
cd research/kafka-signal-bus
cp .env.example .env          # placeholders only; never commit .env
docker compose up -d          # Kafka on 127.0.0.1:9092
docker compose --profile ui up -d   # optional UI on 127.0.0.1:8080
```

Topic convention: `mt5.signals.paper.v1`. Do not create or subscribe to live /
prop topics from this tree.

## Paper stub (log only)

```bash
# Replay the committed example to stdout (default; no Kafka client)
python3 scripts/kafka_signal_bus_stub.py consume --from-file \
  research/kafka-signal-bus/schema/examples/signal_record.paper.v1.json

# Emit one paper example as JSONL (still no broker)
python3 scripts/kafka_signal_bus_stub.py publish-paper
```

`KAFKA_ENABLE` defaults off. A Kafka consume/publish path exists only as an
explicit opt-in when `kafka-python` is installed by the operator. `uv sync`
does not install it. The stub still refuses non-paper topics and never calls
order APIs.

## What this does not do

- Refactor `mql5/Mt5ArchBridge.mq5` or the file bridge client.
- Wire `apps/seven-desk` to Kafka.
- Deploy via `scripts/18-install-forex-indicator.sh` or live launchers.
- Port the MQL5.com article’s binary Produce protocol as production code.
