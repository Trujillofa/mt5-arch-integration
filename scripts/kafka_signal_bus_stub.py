#!/usr/bin/env python3
"""Paper-only Kafka signal-bus stub: validate and log. Never places orders.

Default path is file / stdin / stdout. A Kafka client is optional, off by
default (KAFKA_ENABLE=0), and not a package dependency.

Does not import src/mt5_arch. Does not talk to Seven Desk.
book_mode=live records are logged as dropped / non-actionable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_kafka_signal_schema import (  # noqa: E402
    EXAMPLE_PATH,
    PAPER_TOPIC,
    SignalSchemaError,
    load_records,
    refuse_non_paper_topic,
    validate_record,
)

DEFAULT_BOOTSTRAP = "127.0.0.1:9092"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def disposition_for(record: dict[str, Any]) -> str:
    """paper → log; anything else → drop. Never 'order'."""
    if record.get("book_mode") == "paper":
        return "log"
    return "drop_non_paper"


def format_log_line(record: dict[str, Any], *, source: str) -> str:
    disp = disposition_for(record)
    payload = {
        "event": "kafka_signal_bus_stub",
        "disposition": disp,
        "source": source,
        "logged_at": _utc_now(),
        "schema_version": record.get("schema_version"),
        "symbol": record.get("symbol"),
        "side": record.get("side"),
        "timeframe": record.get("timeframe"),
        "strategy_id": record.get("strategy_id"),
        "terminal_id": record.get("terminal_id"),
        "ts": record.get("ts"),
        "book_mode": record.get("book_mode"),
        "actionable": False,
        "orders": False,
    }
    return json.dumps(payload, separators=(",", ":"))


def emit_lines(records: list[dict[str, Any]], *, source: str, out: TextIO) -> int:
    n_log = 0
    for rec in records:
        line = format_log_line(rec, source=source)
        out.write(line + "\n")
        if disposition_for(rec) == "log":
            n_log += 1
    return n_log


def paper_example() -> dict[str, Any]:
    return validate_record(json.loads(EXAMPLE_PATH.read_text(encoding="utf-8")))


def cmd_consume(args: argparse.Namespace) -> int:
    if args.kafka:
        return _consume_kafka(args)
    path = args.from_file
    if path is None:
        raise SystemExit("consume requires --from-file unless --kafka is set")
    records = load_records(path)
    dest: TextIO
    close = False
    if args.out:
        dest = args.out.open("w", encoding="utf-8")
        close = True
    else:
        dest = sys.stdout
    try:
        n_log = emit_lines(records, source=str(path), out=dest)
    finally:
        if close:
            dest.close()
    print(
        f"kafka-signal-bus-stub consume n={len(records)} logged={n_log} "
        f"actionable=0 orders=0",
        file=sys.stderr,
    )
    return 0


def cmd_publish_paper(args: argparse.Namespace) -> int:
    rec = paper_example()
    if rec.get("book_mode") != "paper":
        raise SystemExit("internal example is not paper; refusing to publish")
    if args.kafka:
        return _publish_kafka(rec, args)
    line = json.dumps(rec, separators=(",", ":"))
    if args.out:
        args.out.write_text(line + "\n", encoding="utf-8")
    else:
        sys.stdout.write(line + "\n")
    print("kafka-signal-bus-stub publish-paper n=1 dest=file-or-stdout", file=sys.stderr)
    return 0


def _require_kafka_enable_and_paper_topic(topic: str) -> None:
    if not _env_truthy("KAFKA_ENABLE"):
        raise SystemExit(
            "KAFKA_ENABLE is not set; refusing to open a broker socket. "
            "File/JSONL mode needs no Kafka client."
        )
    refuse_non_paper_topic(topic)


def _consume_kafka(args: argparse.Namespace) -> int:
    topic = args.topic or os.environ.get("KAFKA_TOPIC", PAPER_TOPIC)
    try:
        _require_kafka_enable_and_paper_topic(topic)
    except SignalSchemaError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        from kafka import KafkaConsumer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "kafka-python is not installed. This stub is file-first; "
            "do not add it to pyproject.toml. Operator-only: pip install kafka-python"
        ) from exc
    bootstrap = args.bootstrap or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP)
    group = args.group or os.environ.get("KAFKA_GROUP_ID", "mt5-arch-research-logger")
    consumer = KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        group_id=group,
        consumer_timeout_ms=args.timeout_ms,
    )
    records: list[dict[str, Any]] = []
    try:
        for msg in consumer:
            records.append(validate_record(json.loads(msg.value.decode("utf-8"))))
    finally:
        consumer.close()
    emit_lines(records, source=f"kafka:{topic}", out=sys.stdout)
    print(
        f"kafka-signal-bus-stub consume-kafka n={len(records)} actionable=0 orders=0",
        file=sys.stderr,
    )
    return 0


def _publish_kafka(rec: dict[str, Any], args: argparse.Namespace) -> int:
    topic = args.topic or os.environ.get("KAFKA_TOPIC", PAPER_TOPIC)
    try:
        _require_kafka_enable_and_paper_topic(topic)
    except SignalSchemaError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        from kafka import KafkaProducer  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "kafka-python is not installed. Use publish-paper without --kafka."
        ) from exc
    bootstrap = args.bootstrap or os.environ.get("KAFKA_BOOTSTRAP_SERVERS", DEFAULT_BOOTSTRAP)
    producer = KafkaProducer(bootstrap_servers=bootstrap)
    key = (rec.get("partition_key") or f"{rec['symbol']}_{rec['timeframe']}").encode("utf-8")
    producer.send(topic, key=key, value=json.dumps(rec).encode("utf-8"))
    producer.flush()
    producer.close()
    print(f"kafka-signal-bus-stub publish-paper n=1 dest=kafka:{topic}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    consume = sub.add_parser("consume", help="Validate and log records (file default)")
    consume.add_argument("--from-file", type=Path, help="JSON / JSONL SignalRecord(s)")
    consume.add_argument("--out", type=Path, help="Write log JSONL here instead of stdout")
    consume.add_argument(
        "--kafka",
        action="store_true",
        help="Opt-in local broker consume (needs KAFKA_ENABLE=1 and kafka-python)",
    )
    consume.add_argument("--bootstrap", default=None)
    consume.add_argument("--topic", default=None)
    consume.add_argument("--group", default=None)
    consume.add_argument("--timeout-ms", type=int, default=2000)
    consume.set_defaults(func=cmd_consume)

    pub = sub.add_parser("publish-paper", help="Emit the committed paper example")
    pub.add_argument("--out", type=Path, help="Write JSONL here instead of stdout")
    pub.add_argument(
        "--kafka",
        action="store_true",
        help="Opt-in local broker publish (needs KAFKA_ENABLE=1 and kafka-python)",
    )
    pub.add_argument("--bootstrap", default=None)
    pub.add_argument("--topic", default=None)
    pub.set_defaults(func=cmd_publish_paper)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
