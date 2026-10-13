"""Offline tests for the research-only Kafka signal-bus scaffold.

No broker, no Wine, no orders. Does not import Seven Desk.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from kafka_signal_bus_stub import (  # noqa: E402
    disposition_for,
    format_log_line,
    paper_example,
)
from verify_kafka_signal_schema import (  # noqa: E402
    EXAMPLE_PATH,
    PAPER_TOPIC,
    SCHEMA_VERSION,
    SignalSchemaError,
    is_paper_topic,
    load_schema,
    refuse_non_paper_topic,
    validate_file,
    validate_record,
)

VERIFY = ROOT / "scripts" / "verify_kafka_signal_schema.py"
STUB = ROOT / "scripts" / "kafka_signal_bus_stub.py"
COMPOSE = ROOT / "research" / "kafka-signal-bus" / "docker-compose.yml"
ADR = ROOT / "docs" / "adr" / "0001-kafka-signal-bus.md"
HOWTO = ROOT / "docs" / "research" / "KAFKA-SIGNAL-BUS.md"
MQL = ROOT / "mql5" / "Include" / "research" / "KafkaSignalPaperContract.mqh"
INSTALLER = ROOT / "scripts" / "18-install-forex-indicator.sh"
PLATFORM_SRC = ROOT / "src" / "mt5_arch"
SEVEN_DESK = ROOT / "apps" / "seven-desk"
def _paper() -> dict:
    return json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))


def test_committed_example_validates():
    rec = validate_file(EXAMPLE_PATH)
    assert rec["schema_version"] == SCHEMA_VERSION
    assert rec["book_mode"] == "paper"
    assert rec["side"] == "buy"


def test_schema_required_matches_verifier():
    schema = load_schema()
    assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
    required = set(schema["required"])
    assert required == {
        "schema_version",
        "symbol",
        "side",
        "timeframe",
        "strategy_id",
        "terminal_id",
        "ts",
        "book_mode",
    }


def test_missing_required_refuses(tmp_path: Path):
    raw = _paper()
    del raw["symbol"]
    with pytest.raises(SignalSchemaError, match="symbol"):
        validate_record(raw)


def test_secret_key_refuses():
    raw = _paper()
    raw["mt5_password"] = "nope"
    with pytest.raises(SignalSchemaError, match="secret key"):
        validate_record(raw)


def test_order_intent_key_refuses():
    raw = _paper()
    raw["lots"] = 0.01
    with pytest.raises(SignalSchemaError, match="order-intent"):
        validate_record(raw)


def test_boolean_live_true_refuses():
    raw = _paper()
    raw["live"] = True
    with pytest.raises(SignalSchemaError, match="live=true"):
        validate_record(raw)


def test_live_book_mode_is_structurally_valid_but_not_actionable():
    raw = _paper()
    raw["book_mode"] = "live"
    rec = validate_record(raw)
    assert rec["book_mode"] == "live"
    assert disposition_for(rec) == "drop_non_paper"
    line = json.loads(format_log_line(rec, source="test"))
    assert line["actionable"] is False
    assert line["orders"] is False
    assert line["disposition"] == "drop_non_paper"


def test_paper_disposition_is_log_only():
    rec = paper_example()
    assert disposition_for(rec) == "log"
    line = json.loads(format_log_line(rec, source="test"))
    assert line["actionable"] is False
    assert line["orders"] is False


def test_verify_cli_example_exits_zero():
    proc = subprocess.run(
        [sys.executable, str(VERIFY), str(EXAMPLE_PATH)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASSED" in proc.stdout


def test_stub_consume_from_file(tmp_path: Path):
    out = tmp_path / "log.jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            str(STUB),
            "consume",
            "--from-file",
            str(EXAMPLE_PATH),
            "--out",
            str(out),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    rows = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln]
    assert len(rows) == 1
    assert rows[0]["disposition"] == "log"
    assert rows[0]["orders"] is False
    assert "actionable=0" in proc.stderr


def test_stub_publish_paper_stdout():
    proc = subprocess.run(
        [sys.executable, str(STUB), "publish-paper"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    rec = json.loads(proc.stdout.strip())
    assert rec["book_mode"] == "paper"
    validate_record(rec)


def test_stub_kafka_without_enable_refuses():
    env = {k: v for k, v in os.environ.items() if k != "KAFKA_ENABLE"}
    proc = subprocess.run(
        [sys.executable, str(STUB), "consume", "--kafka"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode != 0
    assert "KAFKA_ENABLE" in proc.stderr


def test_refuse_live_and_prop_topics():
    assert is_paper_topic(PAPER_TOPIC) is True
    with pytest.raises(SignalSchemaError, match="live"):
        refuse_non_paper_topic("mt5.signals.live.v1")
    with pytest.raises(SignalSchemaError, match="prop-flavored|non-paper"):
        refuse_non_paper_topic("mt5.signals.ftmo.v1")
    with pytest.raises(SignalSchemaError):
        refuse_non_paper_topic("mt5-signals")


def test_compose_is_localhost_paper_only():
    text = COMPOSE.read_text(encoding="utf-8")
    assert "RESEARCH-ONLY" in text
    assert "127.0.0.1:9092:9092" in text
    assert "mt5.signals.paper.v1" in text
    assert "mt5.signals.live" not in text
    assert "OrderSend" not in text
    data = yaml.safe_load(text)
    ports = data["services"]["kafka"]["ports"]
    assert all(str(p).startswith("127.0.0.1:") for p in ports)
    ui_ports = data["services"]["kafka-ui"]["ports"]
    assert all(str(p).startswith("127.0.0.1:") for p in ui_ports)


def test_adr_and_howto_state_file_bridge_truth_and_reject_list():
    adr = ADR.read_text(encoding="utf-8")
    howto = HOWTO.read_text(encoding="utf-8")
    blob = adr + "\n" + howto
    for needle in (
        "file bridge",
        "Seven Desk",
        "Order consumers",
        "promote=no",
        "live_go=false",
        "funded prefixes",
        "Merge ≠ host deploy",
        "Mt5ArchBridge",
        "REJECT",
        "Phase C",
    ):
        assert needle in blob, needle


def test_mql_contract_is_paper_only_no_transport():
    text = MQL.read_text(encoding="utf-8")
    code = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("//")
    )
    assert "KAFKA_SIGNAL_SCHEMA_VERSION" in text
    assert "book_mode" in text
    assert "paper" in text
    forbidden = (
        "OrderSend",
        "OrderClose",
        "PositionOpen",
        "SocketCreate",
        "SocketConnect",
        "KafkaBuildProduce",
        "RecordBatch",
    )
    for tok in forbidden:
        assert tok not in code, tok


def test_installer_does_not_deploy_kafka_research():
    text = INSTALLER.read_text(encoding="utf-8")
    assert "KafkaSignal" not in text
    assert "kafka-signal-bus" not in text
    assert "Include/research" not in text


def test_platform_and_seven_desk_have_no_kafka_imports():
    hits: list[str] = []
    for folder in (PLATFORM_SRC, SEVEN_DESK / "src"):
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js"}:
                continue
            blob = path.read_text(encoding="utf-8", errors="replace").lower()
            if "kafka" in blob:
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_cli_modules_are_not_in_mt5_arch():
    assert not (PLATFORM_SRC / "kafka_signal_bus_stub.py").exists()
    assert "kafka" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
