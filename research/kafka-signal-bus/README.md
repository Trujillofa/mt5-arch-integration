# research/kafka-signal-bus

**RESEARCH-ONLY.** Local paper/dev Kafka plus a versioned signal schema.

- Do **not** deploy this compose on an OMARCHY / Seven Desk host as part of merge.
- Do **not** point funded Wine prefixes at these brokers.
- Do **not** treat topic records as account, position, or order truth.
- File bridge (`Mt5ArchBridge`) stays authoritative for Seven Desk.

Policy: [`docs/adr/0001-kafka-signal-bus.md`](../../docs/adr/0001-kafka-signal-bus.md).

## Layout

| Path | Role |
|------|------|
| `docker-compose.yml` | Single-node Kafka (KRaft), localhost bind |
| `.env.example` | Placeholder env (copy to gitignored `.env`) |
| `schema/signal_record.v1.json` | JSON Schema for `SignalRecord` |
| `schema/examples/signal_record.paper.v1.json` | Valid paper example |

Python (repo `scripts/`, stdlib, no new package deps):

- `scripts/verify_kafka_signal_schema.py`
- `scripts/kafka_signal_bus_stub.py` (log-only consumer / paper publisher)

MQL5 contract only (no sockets, no `OrderSend`, **not** installed by
`scripts/18-install-forex-indicator.sh`):

- `mql5/Include/research/KafkaSignalPaperContract.mqh`

## Run compose

```bash
cp .env.example .env
docker compose up -d
# optional UI
docker compose --profile ui up -d
```

Broker for host processes: `127.0.0.1:9092`.  
Paper topic created by the init service: `mt5.signals.paper.v1`.

Tear down:

```bash
docker compose --profile ui down
```

## Topic naming

| Topic | Use |
|-------|-----|
| `mt5.signals.paper.v1` | Paper / research signals (the only topic this compose creates) |
| `mt5.telemetry.paper.v1` | Reserved name; not created here |
| `mt5.signals.live.v1` | **Do not create** in this tree |

Keys: `{symbol}_{timeframe}` when you need per-instrument order.

## Env placeholders

See `.env.example`. `KAFKA_ENABLE=0` is the required default. Never commit real
bootstrap lists, SASL passwords, or broker account hosts.
