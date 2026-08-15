"""MQL5 ↔ Python HTF Fib parity: buffers, timestamps, ATR, confirmation."""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_mql5_python_parity as parity  # noqa: E402
from htf_fib_core import expand_fib_states, true_range, wilder_atr  # noqa: E402
from verify_mql5_python_parity import (  # noqa: E402
    DEFAULT_FIXTURE,
    FIB_618,
    FIB_786,
    FIB_LIVE_FROM,
    HTF_FIB_BUFFERS,
    PLANTED_CONFIRM_HIGH,
    PLANTED_CONFIRM_LOW,
    PLANTED_HIGH_CENTER,
    PLANTED_HIGH_PRICE,
    PLANTED_LOW_CENTER,
    PLANTED_LOW_PRICE,
    SIGNAL_BUFFER,
    SIGNAL_SHIFT,
    ParityError,
    load_fixture,
    repo_htf_fib_ver,
    verify_fixture,
    write_synthetic_fixture,
)

INDICATOR = ROOT / "mql5" / "Indicators" / "ForexHtfPivotsFib.mq5"
LOGGER = ROOT / "mql5" / "Experts" / "ForexSignalLogger.mq5"
UTILS = ROOT / "mql5" / "Include" / "ForexUtils.mqh"


def test_committed_fixture_passes():
    report = verify_fixture(DEFAULT_FIXTURE)
    assert report["ok"] is True
    assert report["n_bars"] >= 32
    assert report["n_pivots"] >= 2
    assert report["signal_buffer"] == 8


def test_write_synthetic_roundtrip(tmp_path: Path):
    dest = write_synthetic_fixture(tmp_path / "fresh")
    report = verify_fixture(dest)
    assert report["ok"] is True
    assert dest.joinpath("manifest.json").is_file()
    assert dest.joinpath("bars.csv").is_file()
    assert dest.joinpath("pivots.csv").is_file()


def test_buffer_contract_signal_is_8():
    assert SIGNAL_BUFFER == 8
    assert HTF_FIB_BUFFERS[8] == "signal"
    assert HTF_FIB_BUFFERS[7] == "swing_dir"
    assert SIGNAL_SHIFT == 1
    fx = load_fixture(DEFAULT_FIXTURE)
    assert int(fx.manifest["signal_buffer"]) == 8


def test_indicator_setindexbuffer_matches_contract():
    src = INDICATOR.read_text()
    found: dict[int, str] = {}
    for match in re.finditer(
        r"SetIndexBuffer\((\d+),\s*(Buf\w+)",
        src,
    ):
        found[int(match.group(1))] = match.group(2)
    expected = {
        0: "BufEmaFast",
        1: "BufEmaSlow",
        2: "BufEmaBias",
        3: "BufLong",
        4: "BufShort",
        5: "BufFib618",
        6: "BufFib786",
        7: "BufSwingDir",
        8: "BufSignal",
        9: "BufRsi",
        10: "BufRsiMa",
    }
    assert found == expected
    assert "SetIndexBuffer(8, BufSignal" in src
    # Stale header used to say buffer 7.
    assert "iCustom signal buffer = 8" in src


def test_logger_and_howto_use_buffer_8():
    logger = LOGGER.read_text()
    assert "InpSignalBuffer    = 8" in logger
    howto = (ROOT / "docs" / "HOWTO-HTF-FIB.md").read_text()
    assert "iCustom signal buffer: `8`" in howto
    readme = (ROOT / "mql5" / "README.md").read_text()
    assert "**8** | **Signal" in readme
    # The pre-1.42 table listed signal as 7 — that must not return.
    assert "CopyBuffer(handle, 7, 1, 1, sig)" not in readme


def test_forming_bar_signal_is_zero():
    fx = load_fixture(DEFAULT_FIXTURE)
    assert fx.signal[-1] == 0


def test_forming_bar_nonzero_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "forming"))
    rows = dest.joinpath("buffers.csv").read_text().splitlines()
    last = rows[-1].split(",")
    last[-1] = "1"
    rows[-1] = ",".join(last)
    dest.joinpath("buffers.csv").write_text("\n".join(rows) + "\n")
    with pytest.raises(ParityError, match="forming bar"):
        verify_fixture(dest)


def test_pivot_confirm_equals_center_plus_right():
    fx = load_fixture(DEFAULT_FIXTURE)
    right = int(fx.manifest["right"])
    assert fx.pivots
    for p in fx.pivots:
        assert p["confirm_idx"] == p["center_idx"] + right


def test_lookahead_stamp_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "lookahead"))
    rows = dest.joinpath("pivots.csv").read_text().splitlines()
    header, first, *rest = rows
    cols = first.split(",")
    cols[1] = cols[0]  # confirm_idx = center_idx
    dest.joinpath("pivots.csv").write_text(
        "\n".join([header, ",".join(cols), *rest]) + "\n"
    )
    with pytest.raises(ParityError, match="confirm_idx"):
        verify_fixture(dest)


def test_partial_copy_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "short"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["copy"]["rates"]["copied"] = man["copy"]["rates"]["requested"] - 1
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="copied"):
        verify_fixture(dest)


def test_missing_copy_block_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "nocopy"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    del man["copy"]
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="copy"):
        verify_fixture(dest)


def test_wrong_signal_buffer_map_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "buf7"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["signal_buffer"] = 7
    man["buffer_map"]["7"] = "signal"
    man["buffer_map"]["8"] = "swing_dir"
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="buffer"):
        verify_fixture(dest)


def test_timestamps_must_be_chronological(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "rev"))
    bars = dest.joinpath("bars.csv").read_text().splitlines()
    buffers = dest.joinpath("buffers.csv").read_text().splitlines()
    # Swap first two data rows so time goes backwards.
    bars[1], bars[2] = bars[2], bars[1]
    buffers[1], buffers[2] = buffers[2], buffers[1]
    dest.joinpath("bars.csv").write_text("\n".join(bars) + "\n")
    dest.joinpath("buffers.csv").write_text("\n".join(buffers) + "\n")
    dest.joinpath("htf_bars.csv").write_text(dest.joinpath("bars.csv").read_text())
    with pytest.raises(ParityError, match="chronological"):
        verify_fixture(dest)


def test_wilder_atr_matches_fx_series_formula():
    high = np.array([10.0, 11.0, 12.5, 12.0, 13.0, 12.2, 14.0, 13.5])
    low = np.array([9.0, 9.5, 10.0, 10.5, 11.0, 11.2, 12.0, 12.5])
    close = np.array([9.5, 10.5, 11.0, 11.5, 12.0, 12.0, 13.0, 13.0])
    period = 3
    got = wilder_atr(high, low, close, period)
    assert np.isnan(got[0]) and np.isnan(got[1]) and np.isnan(got[2])
    tr_sum = 0.0
    for i in range(1, period + 1):
        tr_sum += true_range(high[i], low[i], close[i - 1])
    assert got[period] == pytest.approx(tr_sum / period)
    for i in range(period + 1, len(high)):
        tr = true_range(high[i], low[i], close[i - 1])
        expect = (got[i - 1] * (period - 1) + tr) / period
        assert got[i] == pytest.approx(expect)


def test_sma_atr_does_not_match_wilder():
    fx = load_fixture(DEFAULT_FIXTURE)
    tr = np.full(len(fx.close), np.nan)
    for i in range(1, len(fx.close)):
        tr[i] = true_range(fx.high[i], fx.low[i], fx.close[i - 1])
    period = 14
    sma = np.full(len(fx.close), np.nan)
    for i in range(period, len(fx.close)):
        sma[i] = float(np.nanmean(tr[i - period + 1 : i + 1]))
    wilder = wilder_atr(fx.high, fx.low, fx.close, period)
    # After the seed bar the recurrences diverge on this series.
    tail = slice(period + 5, None)
    assert not np.allclose(sma[tail], wilder[tail], equal_nan=True)
    assert np.allclose(fx.atr14[tail], wilder[tail], equal_nan=True)


def test_utils_atr_comment_is_wilder():
    text = UTILS.read_text()
    assert "Wilder ATR series" in text
    assert "out_atr[period] = tr_sum / period" in text


def test_export_script_is_non_trading():
    src = (ROOT / "mql5" / "Scripts" / "ExportHtfFibParityFixture.mq5").read_text()
    assert "OrderSend(" not in src
    assert "CTrade" not in src
    assert "InpSignalBuffer    = 8" in src
    assert "FxAtrSeries" in src
    assert "confirm = c + InpRight" in src
    assert "iCustom(sym, chart_tf, InpIndicatorName)" in src
    assert "htf_fib_effective_" in src
    assert "DeleteLeftoverSidecar" in src
    assert src.index("DeleteLeftoverSidecar") < src.index("iCustom(sym, chart_tf")
    assert "sidecar not recreated after iCustom" in src
    assert "FAIL sidecar symbol=" in src
    assert "FAIL sidecar chart_tf=" in src
    assert "indicator_left" in src
    assert "TIME_DATE | TIME_SECONDS" in src
    assert "hn_closed" in src
    assert "WriteCopyFail" in src
    assert "FX_HTF_PIVOT_SCAN_BARS" in src


def test_hand_derived_pivots_and_fibs():
    """Independent of htf_fib_core: planted geometry and directional fibs."""
    assert pytest.approx(101.46) == FIB_618
    assert pytest.approx(96.42) == FIB_786
    fx = load_fixture(DEFAULT_FIXTURE)
    got = [
        (p["center_idx"], p["confirm_idx"], p["ptype"], p["price"])
        for p in fx.pivots
    ]
    assert got == [
        (PLANTED_LOW_CENTER, PLANTED_CONFIRM_LOW, -1, PLANTED_LOW_PRICE),
        (PLANTED_HIGH_CENTER, PLANTED_CONFIRM_HIGH, 1, PLANTED_HIGH_PRICE),
    ]
    # Same-TF: fib live on the confirmation bar, not before.
    assert np.isnan(fx.fib_618[PLANTED_CONFIRM_HIGH - 1])
    assert fx.swing_dir[PLANTED_CONFIRM_HIGH - 1] == 0
    assert fx.fib_618[FIB_LIVE_FROM] == pytest.approx(FIB_618)
    assert fx.swing_dir[FIB_LIVE_FROM] == 1
    assert fx.signal[FIB_LIVE_FROM] == 1


def test_hand_derived_atr_seed_independent_of_wilder_atr():
    fx = load_fixture(DEFAULT_FIXTURE)
    period = 14
    tr_sum = 0.0
    for i in range(1, period + 1):
        hl = fx.high[i] - fx.low[i]
        hc = abs(fx.high[i] - fx.close[i - 1])
        lc = abs(fx.low[i] - fx.close[i - 1])
        tr_sum += max(hl, hc, lc)
    seed = tr_sum / period
    assert fx.atr14[period] == pytest.approx(seed, abs=1e-8)
    i = period + 1
    hl = fx.high[i] - fx.low[i]
    hc = abs(fx.high[i] - fx.close[i - 1])
    lc = abs(fx.low[i] - fx.close[i - 1])
    step = (seed * (period - 1) + max(hl, hc, lc)) / period
    assert fx.atr14[i] == pytest.approx(step, abs=1e-8)


def test_write_synthetic_byte_matches_committed(tmp_path: Path):
    dest = write_synthetic_fixture(tmp_path / "regen")
    for name in (
        "manifest.json",
        "bars.csv",
        "htf_bars.csv",
        "buffers.csv",
        "pivots.csv",
    ):
        assert dest.joinpath(name).read_bytes() == (
            DEFAULT_FIXTURE.joinpath(name).read_bytes()
        )


def test_expand_fib_states_mutation_fails(monkeypatch: pytest.MonkeyPatch):
    def leaky(n, states):
        leaked = [(max(0, a - 5), d, x, y) for a, d, x, y in states]
        return expand_fib_states(n, leaked)

    monkeypatch.setattr(parity, "expand_fib_states", leaky)
    with pytest.raises(ParityError):
        verify_fixture(DEFAULT_FIXTURE)


def test_wilder_atr_mutation_fails(monkeypatch: pytest.MonkeyPatch):
    def bogus(high, low, close, period=14):
        return np.full(len(high), 1.23)

    monkeypatch.setattr(parity, "wilder_atr", bogus)
    with pytest.raises(ParityError, match="atr14"):
        verify_fixture(DEFAULT_FIXTURE)


def test_equal_length_different_tf_refuses_identity(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "mtf"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["chart_tf"] = "H1"
    man["htf_tf"] = "H4"
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="equal bar counts"):
        verify_fixture(dest)


def test_missing_htf_bars_raises(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "nohtf"))
    dest.joinpath("htf_bars.csv").unlink()
    with pytest.raises(ParityError, match="htf_bars"):
        verify_fixture(dest)


def test_missing_right_raises(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "noright"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    del man["right"]
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="right"):
        verify_fixture(dest)


def test_export_ok_must_be_true(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "notok"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["export_ok"] = False
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="export_ok"):
        verify_fixture(dest)


def test_abs_tol_must_be_sane(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "tol"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["abs_tol"] = 1.0
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="abs_tol"):
        verify_fixture(dest)


def test_mtf_activation_uses_available_at():
    """H1 row is eligible only when its close >= H4 confirm open + 4h."""
    from datetime import datetime, timedelta

    confirm_open = datetime(2024, 1, 2, 12, 0, 0)
    available = parity.htf_available_at(confirm_open, "H4")
    assert available == confirm_open + timedelta(hours=4)
    h1_during = datetime(2024, 1, 2, 14, 0, 0)
    h1_after = datetime(2024, 1, 2, 16, 0, 0)
    assert parity.chart_bar_close(h1_during, "H1") < available
    assert parity.chart_bar_close(h1_after, "H1") >= available


def test_indicator_confirm_stamp_and_no_global_fallback():
    src = INDICATOR.read_text()
    assert "PushFibSnap(t_available[k])" in src
    assert "ChartBarClose(time[k])" in src
    assert "WriteEffectiveConfig" in src
    assert "n_closed" in src
    assert "BufSwingDir[k] = (double)g_swingDir" not in src
    assert "|| true" not in src
    assert "FX_HTF_PIVOT_SCAN_BARS" in src


def test_mql5_export_requires_indicator_pin(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "unpin"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["source"] = "mql5_export"
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="indicator_left"):
        verify_fixture(dest)


def test_synthetic_omits_indicator_version(tmp_path: Path):
    """Synthetic never ran the indicator — a hardcoded version is how 1.44 drifted."""
    fx = load_fixture(DEFAULT_FIXTURE)
    assert "indicator_version" not in fx.manifest
    dest = write_synthetic_fixture(tmp_path / "no_ver")
    written = json.loads(dest.joinpath("manifest.json").read_text())
    assert "indicator_version" not in written


def test_htf_fib_ver_define_feeds_sidecar():
    src = INDICATOR.read_text()
    match = re.search(r'#define\s+HTF_FIB_VER\s+"([^"]+)"', src)
    assert match, "HTF_FIB_VER define missing"
    assert match.group(1)
    assert 'FileWriteString(h, "version=" + HTF_FIB_VER' in src


def test_mql5_export_requires_indicator_version(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "nover"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["source"] = "mql5_export"
    man["htf_tf"] = "H4"
    man["indicator_left"] = int(man["left"])
    man["indicator_right"] = int(man["right"])
    man["indicator_fib_source"] = 0
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="indicator_version"):
        verify_fixture(dest)


def test_mql5_export_pin_mismatch_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "pinmiss"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["source"] = "mql5_export"
    man["htf_tf"] = "H4"
    man["indicator_left"] = 7
    man["indicator_right"] = int(man["right"])
    man["indicator_fib_source"] = 0
    man["indicator_version"] = repo_htf_fib_ver()
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="left/right"):
        verify_fixture(dest)


def test_mql5_export_stale_or_bogus_indicator_version_fails(tmp_path: Path):
    dest = Path(shutil.copytree(DEFAULT_FIXTURE, tmp_path / "stalever"))
    man = json.loads(dest.joinpath("manifest.json").read_text())
    man["source"] = "mql5_export"
    man["htf_tf"] = "H4"
    man["indicator_left"] = int(man["left"])
    man["indicator_right"] = int(man["right"])
    man["indicator_fib_source"] = 0
    man["indicator_version"] = "stale-or-bogus"
    dest.joinpath("manifest.json").write_text(json.dumps(man, indent=2) + "\n")
    with pytest.raises(ParityError, match="HTF_FIB_VER"):
        verify_fixture(dest)


@pytest.mark.live
def test_optional_live_fixture_if_present():
    """Optional: MT5_PARITY_FIXTURE=/path/to/exported/dir."""
    import os

    raw = os.environ.get("MT5_PARITY_FIXTURE", "").strip()
    if not raw:
        pytest.skip("set MT5_PARITY_FIXTURE to a live export directory")
    report = verify_fixture(Path(raw))
    assert report["ok"] is True
    man = json.loads(Path(raw).joinpath("manifest.json").read_text())
    match = re.search(r'#define\s+HTF_FIB_VER\s+"([^"]+)"', INDICATOR.read_text())
    assert match
    assert man.get("indicator_version") == match.group(1)
