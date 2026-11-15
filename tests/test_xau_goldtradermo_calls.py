"""Parser and bar-fill tests for the GOLDTRADERMO call replay.

Fixtures are tiny HTML and synthetic bars. Nothing here reads the
Telegram export or asserts a profit factor from that tape.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import xau_goldtradermo_calls as gtm  # noqa: E402

EXPORT_TZ = timezone(timedelta(hours=-5))
HIT = "\U0001d407\U0001d408\U0001d413"  # mathematical bold HIT


def _html(message_id: str, stamp: str, body: str) -> str:
    return (
        f'<div class="message default clearfix" id="{message_id}">'
        f'<div class="pull_right date details" title="{stamp}">x</div>'
        f'<div class="text">{body}</div></div>'
    )


NORMAL = _html(
    "message10",
    "05.12.2025 10:32:19 UTC-05:00",
    "BUY XAUUSD GOLD 4245/4241<br><br>TP 4248<br>TP 4250<br>TP 4254<br>TP 4258<br>SL 4230",
)
GLITCH = _html(
    "message11",
    "28.11.2025 03:48:25 UTC-05:00",
    "XAUUSD buy 40160<br><br>TP 4163<br>TP 4167<br>TP 4170<br>TP 4174<br>TP 4176<br>SL 4130",
)
TRUNCATED = _html(
    "message12",
    "02.12.2025 09:53:28 UTC-05:00",
    "SELL XAUUSD GOLD 4224/426<br><br>TP 4220<br>TP 4216<br>TP 4212<br>TP 4210<br>SL 4236",
)
TP_HIT = _html(
    "message13",
    "28.11.2025 04:12:43 UTC-05:00",
    f"XAUUSD BUY <br><br>TP 1 {HIT} 30+ PIPS",
)
ALL_TP = _html(
    "message14",
    "28.11.2025 06:00:00 UTC-05:00",
    "XAUUSD BUY <br><br>ALL TP Done",
)


def _page(*blocks: str) -> str:
    return "<html><body>" + "".join(blocks) + "</body></html>"


def test_parser_keeps_a_normal_call_and_drops_marketing_and_bad_prices():
    batch = gtm.parse_html(_page(NORMAL, GLITCH, TRUNCATED, TP_HIT, ALL_TP), source_file="t.html")
    assert batch.tp_hit_messages == 2
    assert len(batch.calls) == 1
    assert len(batch.excluded) == 2
    call = batch.calls[0]
    assert call.message_id == "message10"
    assert call.side == "buy"
    assert call.zone_lo == pytest.approx(4241)
    assert call.zone_hi == pytest.approx(4245)
    assert call.tps == (4248, 4250, 4254, 4258)
    assert call.sl == pytest.approx(4230)
    assert call.nearest_tp == pytest.approx(4248)
    assert call.export_offset == "-05:00"
    assert call.bar_time == datetime(2025, 12, 5, 15, 32, 19)
    assert call.export_time == datetime(2025, 12, 5, 10, 32, 19, tzinfo=EXPORT_TZ)
    reasons = {row.message_id: row.reason for row in batch.excluded}
    assert reasons["message11"] == "digit_length"
    assert reasons["message12"] == "digit_length"
    assert all(row.message_id != "message13" for row in batch.excluded)
    assert "40160" in batch.excluded[0].text or "40160" in batch.excluded[1].text


def test_side_glued_to_zone_is_a_kept_call():
    glued = _html(
        "message12401",
        "09.06.2026 09:51:10 UTC-05:00",
        "XAUUSD SELL4290/4294<br><br>TP 4286<br>TP 4282<br>TP 4278<br>TP 4274<br>SL 4302",
    )
    batch = gtm.parse_html(_page(glued), source_file="messages3.html")
    assert batch.excluded == ()
    assert len(batch.calls) == 1
    call = batch.calls[0]
    assert call.message_id == "message12401"
    assert call.side == "sell"
    assert call.zone_lo == pytest.approx(4290)
    assert call.zone_hi == pytest.approx(4294)
    assert call.tps == (4286, 4282, 4278, 4274)
    assert call.sl == pytest.approx(4302)
    assert call.bar_time == datetime(2026, 6, 9, 14, 51, 10)


def test_wrong_side_tp_is_excluded_not_rewritten():
    bad_tp = _html(
        "message30",
        "23.12.2025 22:24:35 UTC-05:00",
        "SELL XAUUSD GOLD 4495/4497<br>TP 4491<br>TP 4486<br>TP 4480<br>TP 4574<br>SL 4510",
    )
    batch = gtm.parse_html(_page(bad_tp))
    assert batch.calls == ()
    assert batch.excluded[0].reason == "side_geometry"
    assert "4574" in batch.excluded[0].text


def test_double_slash_zone_is_kept_and_three_part_zone_is_excluded():
    kept = _html(
        "message20",
        "29.01.2026 09:52:18 UTC-05:00",
        "#XAUUSD buy 5504//5500<br>TP. 5510<br>TP 5520<br>TP 5530<br>TP 5540<br>SL 5480",
    )
    bad = _html(
        "message21",
        "27.03.2026 06:59:52 UTC-05:00",
        "#XAUUSD Buy 4415/44/11<br>TP 4418<br>TP 4422<br>TP 4426<br>TP 4432<br>SL 4400",
    )
    batch = gtm.parse_html(_page(kept, bad))
    assert [call.message_id for call in batch.calls] == ["message20"]
    assert batch.calls[0].zone_lo == pytest.approx(5500)
    assert batch.calls[0].zone_hi == pytest.approx(5504)
    assert batch.excluded[0].reason == "zone_arity"


def _call(**overrides) -> gtm.Call:
    base = {
        "message_id": "m",
        "source_file": "t.html",
        "export_time": datetime(2025, 12, 5, 10, 0, tzinfo=EXPORT_TZ),
        "export_offset": "-05:00",
        "bar_time": datetime(2025, 12, 5, 15, 0),
        "side": "buy",
        "zone_lo": 100.0,
        "zone_hi": 101.0,
        "tps": (103.0, 105.0),
        "sl": 98.0,
        "text": "BUY XAUUSD GOLD 101/100\nTP 103\nTP 105\nSL 98",
    }
    base.update(overrides)
    return gtm.Call(**base)


def _bar(minute: int, op: float, hi: float, lo: float, cl: float, spread: float | None = None) -> gtm.Bar:
    return gtm.Bar(
        time=datetime(2025, 12, 5, 15, 0) + timedelta(minutes=minute),
        open=op,
        high=hi,
        low=lo,
        close=cl,
        spread=spread,
    )


def _zero_cost(**overrides) -> gtm.CostSpec:
    base = {
        "point_size": 0.01,
        "slippage_points": 0.0,
        "commission_per_lot": 0.0,
        "missing_spread_points": 0.0,
    }
    base.update(overrides)
    return gtm.CostSpec(**base)


def test_fill_tp_trades_first():
    bars = [
        _bar(15, 102.0, 102.4, 101.0, 101.2, spread=10),
        _bar(30, 101.4, 103.4, 101.1, 103.0, spread=10),
    ]
    fill = gtm.fill_call(_call(), bars, _zero_cost())
    assert fill.status == "scored"
    assert fill.reason == "tp"
    assert fill.entry_price == pytest.approx(101.0)
    assert fill.exit_price == pytest.approx(103.0)
    assert fill.entry_bar_time == "2025-12-05 15:15:00"
    assert fill.spread_source == "bar"


def test_fill_sl_trades_first():
    bars = [
        _bar(15, 102.0, 102.4, 101.0, 101.2),
        _bar(30, 101.2, 101.6, 97.5, 98.2),
    ]
    fill = gtm.fill_call(_call(), bars, _zero_cost())
    assert (fill.status, fill.reason) == ("scored", "sl")
    assert fill.exit_price == pytest.approx(98.0)


def test_fill_same_bar_sl_and_tp_is_unresolved():
    bars = [
        _bar(15, 102.0, 102.4, 101.0, 101.2),
        _bar(30, 101.2, 104.0, 97.0, 100.0),
    ]
    fill = gtm.fill_call(_call(), bars, _zero_cost())
    assert fill.status == "unresolved"
    assert fill.reason == "same_bar_sl_and_tp"
    assert fill.pnl is None


def test_fill_no_bar_after_timestamp_is_unresolved():
    bars = [_bar(-30, 102.0, 102.4, 101.0, 101.2)]
    fill = gtm.fill_call(_call(), bars, _zero_cost())
    assert (fill.status, fill.reason) == ("unresolved", "no_bar_after_call")


def test_cost_input_changes_pnl_versus_zero_cost():
    bars = [
        _bar(15, 102.0, 102.4, 101.0, 101.2, spread=None),
        _bar(30, 101.4, 103.4, 101.1, 103.0, spread=None),
    ]
    free = gtm.fill_call(_call(), bars, _zero_cost())
    paid = gtm.fill_call(_call(), bars, _zero_cost(missing_spread_points=20))
    assert free.status == paid.status == "scored"
    assert free.cost == pytest.approx(0.0)
    assert paid.cost is not None and paid.cost > 0
    assert paid.spread_source == "assumption"
    assert free.pnl is not None and paid.pnl is not None
    assert free.pnl - paid.pnl == pytest.approx(paid.cost)
    assert paid.pnl < free.pnl


def test_closed_shape_of_zone_calls_is_no_new_family():
    early = _call(message_id="a", bar_time=datetime(2025, 12, 20, 12, 0))
    late = _call(
        message_id="b",
        export_time=datetime(2026, 3, 2, 9, 0, tzinfo=EXPORT_TZ),
        bar_time=datetime(2026, 3, 2, 14, 0),
    )
    outcome = gtm.closed_shape_outcome([early, late], holdout_utc=gtm.HOLDOUT_NAIVE_UTC)
    assert outcome["outcome"] == "NO_NEW_FAMILY"
    assert outcome["knobs"] is None
    assert outcome["family_id"] is None
    assert outcome["promote"] is False
    assert outcome["live_go"] is False
    assert outcome["PAPER_GO"] == "no"
    blob = " ".join(outcome["reasons"]).lower()
    assert "own-price" in blob
    assert "xau-thesis-pass-2026-10-03.md" in blob
    assert "xau_gold_session_study" in blob
    assert "2026-01-01" in blob
    assert "profit_factor" not in outcome


def test_count_identity_partitions_attempts():
    counts = gtm.count_identity(3, 2, 1, 2)
    assert counts["parsed_total"] == 5
    assert counts["excluded_malformed"] + counts["scored"] + counts["unresolved"] == 5
    assert counts["parsed_calls"] == counts["scored"] + counts["unresolved"]


def test_entry_point_on_a_tiny_export_and_csv(tmp_path: Path):
    export = tmp_path / "export"
    export.mkdir()
    (export / "messages.html").write_text(
        _page(NORMAL, GLITCH, TP_HIT, ALL_TP),
        encoding="utf-8",
    )
    bars = tmp_path / "bars.csv"
    # Call bar time is 15:32:19 UTC, so the 15:30 bar is not eligible.
    bars.write_text(
        "time,timeframe,symbol,open,high,low,close,spread\n"
        "2025-12-05 15:30:00+00:00,M15,XAUUSD,4240,4250,4230,4248,12\n"
        "2025-12-05 15:45:00+00:00,M15,XAUUSD,4246,4246.5,4245,4245.2,12\n"
        "2025-12-05 16:00:00+00:00,M15,XAUUSD,4245.2,4248.4,4245.1,4248,12\n"
        "2025-12-05 15:45:00+00:00,H1,XAUUSD,1,1,1,1,99\n",
        encoding="utf-8",
    )
    costs = tmp_path / "costs.json"
    costs.write_text(
        json.dumps(
            {
                "point_size": 0.01,
                "slippage_points": 0.0,
                "commission_per_lot": 0.0,
            }
        ),
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout.json"
    holdout.write_text(
        json.dumps({"holdout_start": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    out = tmp_path / "replay.json"
    note = tmp_path / "note.md"
    code = gtm.main(
        [
            "--export",
            str(export),
            "--bars",
            str(bars),
            "--costs",
            str(costs),
            "--holdout",
            str(holdout),
            "--out",
            str(out),
            "--note",
            str(note),
        ]
    )
    assert code == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["counts"]["parsed_calls"] == 1
    assert report["counts"]["excluded_malformed"] == 1
    assert report["counts"]["scored"] == 1
    assert report["counts"]["unresolved"] == 0
    assert report["tp_hit_messages"] == 2
    assert report["scored_exits_from_bars"] == 1
    assert report["tp_hit_messages"] != report["scored_exits_from_bars"]
    assert report["tp_hit_is_not_the_win_count"] is True
    assert report["outcome"] == "NO_NEW_FAMILY"
    assert "profit_factor" not in report
    text = note.read_text(encoding="utf-8")
    assert "NO_NEW_FAMILY" in text
    assert "UTC-05:00" in text
    assert "not the win count" in text
    assert "XAU-THESIS-PASS-2026-10-03.md" in text
    assert report["calls"][0]["exit_bar_time"] == "2025-12-05 16:00:00"
    assert report["calls"][0]["entry_bar_time"] == "2025-12-05 15:45:00"
    assert report["calls"][0]["reason"] == "tp"
