"""Path 2 lock, unused SQL/compose sketch, synthetic MqlTick CVD. No Docker."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tick_cvd_core import (  # noqa: E402
    MQL_TICK_CSV_COLUMNS,
    MqlTickRow,
    cvd_series,
    feed_populate_audit,
    flag_direction_ratio,
    last_trade_ratio,
    parse_mql_tick_csv,
    refuse_bar_ohlcv_cvd,
    volume_populated_ratio,
)

LOCK_PATH = ROOT / "results" / "timescale_true_cvd_v1_lock.json"
SCHEMA_PATH = ROOT / "docs" / "research" / "timescale" / "schema.sql"
COMPOSE_PATH = ROOT / "docs" / "research" / "timescale" / "docker-compose.yml"
FIXTURE = ROOT / "tests" / "fixtures" / "ticks" / "mql_tick_sample.csv"
SEARCH_ID = "timescale_true_cvd_v1"


def test_lock_is_infra_not_a_screen():
    lock = json.loads(LOCK_PATH.read_text())
    assert lock["search_id"] == SEARCH_ID
    assert lock["architecture_id"] == SEARCH_ID
    assert lock["kind"] == "infra_architecture"
    assert lock["path"] == "2"
    assert lock["instruments"] == "TBD"
    assert lock["symbol"] is None
    assert lock["broker"] is None
    assert lock["promote"] is False
    assert lock["live_go"] is False
    assert lock["python_only"] is True
    assert lock["n_configs_expected"] == 0
    assert lock["selection_end"] is None
    assert lock["holdout_start"] is None
    assert lock["stood_up"]["timescaledb"] is False
    assert lock["stood_up"]["docker_compose_up"] is False
    assert lock["stood_up"]["copyticks_export"] is False
    assert lock["stood_up"]["ohlcv_screen"] is False
    assert lock["tick_inventory_2026_08_19"]["research_store"] == "none"
    assert lock["tick_inventory_2026_08_19"]["parseable_mql_tick_csv"] == "none"
    assert lock["tick_inventory_2026_08_19"]["wine_tkc_is_research_store"] is False
    assert "US100" not in (lock.get("symbol") or "")
    not_in = " ".join(lock["not_in_scope"])
    assert "tick_volume" in not_in
    assert "US100" in not_in
    assert "xau_loop_status" in not_in


def test_lock_forbids_proxy_and_tkc():
    lock = json.loads(LOCK_PATH.read_text())
    falsifiers = " ".join(lock["falsifiers"])
    assert "tick_volume" in falsifiers
    assert ".tkc" in falsifiers or "tkc" in falsifiers
    assert lock["cvd"]["not"].find("tick_proxy_cvd") >= 0


def test_schema_sql_sanity():
    sql = SCHEMA_PATH.read_text()
    for col in (
        "broker",
        "symbol",
        "source",
        "time_utc",
        "time_msc",
        "seq",
        "bid",
        "ask",
        "last",
        "volume",
        "volume_real",
        "flags",
        "server_utc_offset_sec",
    ):
        assert col in sql, col
    assert "create_hypertable" in sql
    assert "source <> 'tkc'" in sql
    assert "copyticks_csv" in sql
    assert "UNUSED" in sql.splitlines()[0] or "UNUSED" in sql[:200]
    assert "cvd_bars" not in sql


def test_compose_is_localhost_unstarted_sketch():
    yml = COMPOSE_PATH.read_text()
    assert "UNSTARTED" in yml
    assert "127.0.0.1:15433:5432" in yml
    assert "15432" in yml  # documented collision avoid
    assert "0.0.0.0" not in yml
    assert "restart: \"no\"" in yml or "restart: 'no'" in yml


def test_synthetic_fixture_true_cvd():
    rows = parse_mql_tick_csv(FIXTURE)
    assert len(rows) == 6
    assert all(r.source == "synthetic" for r in rows)
    series = cvd_series(rows)
    kinds = [s.kind for s in series]
    assert kinds[0] == "quote_only"
    assert kinds[1] == "quote_only"
    assert kinds[2] == "true_buy"
    assert kinds[3] == "true_sell"
    assert kinds[4] == "inferred_last_at_or_above_ask"
    assert kinds[5] == "inferred_last_below_mid"
    assert series[0].cvd_true == 0.0
    assert series[1].cvd_true == 0.0
    assert series[2].cvd_true == 1.5
    assert series[3].cvd_true == 1.0
    # inferred last-vs-BBO must not move true CVD
    assert series[4].cvd_true == 1.0
    assert series[5].cvd_true == 1.0
    assert series[4].cvd_inferred == 3.0
    assert series[5].cvd_inferred == 2.0


def test_refuse_ohlcv_as_tick_tape():
    try:
        refuse_bar_ohlcv_cvd(["time", "open", "high", "low", "close", "tick_volume"])
    except ValueError as exc:
        assert "tick_volume" in str(exc) or "OHLC" in str(exc)
    else:
        raise AssertionError("expected refuse_bar_ohlcv_cvd to raise")


def test_refuse_tkc_source(tmp_path: Path):
    bad = tmp_path / "tkc.csv"
    header = ",".join(MQL_TICK_CSV_COLUMNS)
    bad.write_text(
        header
        + "\n171,0,1,2,0,0,0,2,X,fp,tkc,10800\n",
        encoding="utf-8",
    )
    try:
        parse_mql_tick_csv(bad)
    except ValueError as exc:
        assert "tkc" in str(exc)
    else:
        raise AssertionError("expected tkc source to raise")


def test_csv_columns_match_lock_contract():
    header = FIXTURE.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == MQL_TICK_CSV_COLUMNS


def _row(**kwargs) -> MqlTickRow:
    base = {
        "time_msc": 1,
        "seq": 0,
        "bid": 1.0,
        "ask": 1.1,
        "last": 0.0,
        "volume": 0,
        "volume_real": 0.0,
        "flags": 2,
        "symbol": "SYNTH",
        "broker": "none",
        "source": "synthetic",
        "server_utc_offset_sec": 0,
    }
    base.update(kwargs)
    return MqlTickRow(**base)


def test_populate_ratios_on_synthetic_fixture():
    rows = parse_mql_tick_csv(FIXTURE)
    assert last_trade_ratio(rows) == 4 / 6
    assert volume_populated_ratio(rows) == 4 / 6
    assert flag_direction_ratio(rows) == 2 / 6
    audit = feed_populate_audit(rows)
    assert audit["verdict"] == "QUALIFY"
    assert audit["n_ticks"] == 6


def test_populate_disqualify_when_last_all_zero():
    rows = [
        _row(time_msc=1, last=0.0, volume=0, volume_real=0.0, flags=6),
        _row(time_msc=2, last=0.0, volume=1, volume_real=0.0, flags=38),
    ]
    audit = feed_populate_audit(rows)
    assert last_trade_ratio(rows) == 0.0
    assert audit["verdict"] == "DISQUALIFY"
    assert "last==0" in audit["reason"]
    assert "tick_volume" in audit["reason"]


def test_populate_disqualify_last_without_size_or_flags():
    rows = [_row(time_msc=1, last=100.0, volume=0, volume_real=0.0, flags=8)]
    audit = feed_populate_audit(rows)
    assert last_trade_ratio(rows) == 1.0
    assert volume_populated_ratio(rows) == 0.0
    assert flag_direction_ratio(rows) == 0.0
    assert audit["verdict"] == "DISQUALIFY"


def test_populate_empty_tape_disqualify():
    audit = feed_populate_audit([])
    assert audit["n_ticks"] == 0
    assert audit["verdict"] == "DISQUALIFY"


def test_export_script_is_copyticks_not_orders():
    script = ROOT / "mql5" / "Scripts" / "ExportTicksCopyRange.mq5"
    include = ROOT / "mql5" / "Include" / "TickCopyRangeExport.mqh"
    text = script.read_text() + "\n" + include.read_text()
    assert "CopyTicksRange" in text
    assert "COPY_TICKS_ALL" in text
    assert "OrderSend(" not in text
    assert "ExpertRemove(" not in text
    assert "TerminalClose(" not in text
    assert "copyticks_csv" in text
