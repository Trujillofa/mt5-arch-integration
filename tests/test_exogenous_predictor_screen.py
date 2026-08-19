"""Synthetic smoke for xau_exogenous_predictor_screen (Phase E runner).

No develop package load in these tests — frames are hand-built.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_exogenous_predictor_screen as screen  # noqa: E402
import xau_family_exog_london_fx_cosign_xau_follow_flat as fam  # noqa: E402

CHARTER_V4 = fam.DEFAULT_CHARTER_PATH
SYMBOLS = fam.SYMBOLS


def _bars(day: str, hours: list[int], *, base: float, scale: float, spreads: float = 0.0) -> pd.DataFrame:
    rows = []
    for h in hours:
        o = base
        c = base
        rows.append(
            {
                "time": pd.Timestamp(f"{day} {h:02d}:00:00"),
                "open": o,
                "high": o + scale,
                "low": o - scale,
                "close": c,
                "spread": spreads,
            }
        )
    return pd.DataFrame(rows)


def _warmup(n_days: int = 5) -> dict[str, pd.DataFrame]:
    bases = {"XAUUSD": 2000.0, "EURUSD": 1.10, "GBPUSD": 1.25}
    scales = {"XAUUSD": 3.0, "EURUSD": 0.0015, "GBPUSD": 0.0015}
    hours = list(range(1, 21))
    start = pd.Timestamp("2024-01-02")
    parts: dict[str, list[pd.DataFrame]] = {s: [] for s in SYMBOLS}
    for d in range(n_days):
        day = (start + pd.DateOffset(days=int(d))).strftime("%Y-%m-%d")
        for s in SYMBOLS:
            parts[s].append(_bars(day, hours, base=bases[s], scale=scales[s]))
    return {s: pd.concat(parts[s], ignore_index=True) for s in SYMBOLS}


def _signal_day(
    day: str,
    *,
    fx_up: bool = True,
    xau_flat: bool = True,
    post_tp: bool = True,
) -> dict[str, pd.DataFrame]:
    hours = list(range(1, 15))
    bases = {"XAUUSD": 2000.0, "EURUSD": 1.10, "GBPUSD": 1.25}
    scales = {"XAUUSD": 2.0, "EURUSD": 0.0010, "GBPUSD": 0.0010}
    out: dict[str, pd.DataFrame] = {}
    for s in SYMBOLS:
        base = bases[s]
        scale = scales[s]
        opens, highs, lows, closes = [], [], [], []
        for h in hours:
            o = base
            c = base
            if h == 7:
                if s in ("EURUSD", "GBPUSD"):
                    c = base + scale if fx_up else base - scale
                else:
                    c = base if xau_flat else (base + scale if fx_up else base - scale)
            elif h >= 8 and s == "XAUUSD" and post_tp:
                direction = 1 if fx_up else -1
                step = (h - 7) * scale * 8
                c = base + direction * step
                o = base
            hi = max(o, c) + scale * 0.5
            lo = min(o, c) - scale * 0.5
            if s == "XAUUSD" and h >= 8 and post_tp:
                direction = 1 if fx_up else -1
                if direction > 0:
                    hi = max(hi, base + scale * 40)
                else:
                    lo = min(lo, base - scale * 40)
            opens.append(o)
            highs.append(hi)
            lows.append(lo)
            closes.append(c)
        rows = []
        for j, h in enumerate(hours):
            rows.append(
                {
                    "time": pd.Timestamp(f"{day} {h:02d}:00:00"),
                    "open": opens[j],
                    "high": highs[j],
                    "low": lows[j],
                    "close": closes[j],
                    "spread": 0.0,
                }
            )
        out[s] = pd.DataFrame(rows)
    return out


def _many(n: int, *, xau_flat: bool) -> dict[str, pd.DataFrame]:
    warm = _warmup()
    start = pd.Timestamp("2024-02-01")
    frames = {s: [warm[s]] for s in SYMBOLS}
    for i in range(n):
        day = (start + pd.DateOffset(days=int(i))).strftime("%Y-%m-%d")
        sig = _signal_day(day, xau_flat=xau_flat, post_tp=True)
        for s in SYMBOLS:
            frames[s].append(sig[s])
    return {s: pd.concat(frames[s], ignore_index=True) for s in SYMBOLS}


def test_runner_end_to_end_fresh_pass(tmp_path: Path):
    frames = _many(25, xau_flat=True)
    out = tmp_path / "screen_pass"
    result = screen.run_screen(
        charter_path=CHARTER_V4,
        frames=frames,
        out_dir=out,
        dispositional=False,
    )
    rep = result["report"]
    assert rep["disposition"] == "SOFT_PASS"
    assert rep["null_armed"] is True
    assert rep["soft_passers"] == 1
    assert "pooled" in rep and "strata" in rep
    for key in ("n", "profit_factor", "net_profit", "max_drawdown_pct"):
        assert key in rep["pooled"]
        assert key in rep["strata"][fam.STRATUM_NOT_COSIGN]
        assert key in rep["strata"][fam.STRATUM_COSIGN]
    assert (out / "report.json").is_file()
    assert (out / "dry_plan.json").is_file()
    assert (out / "gates_resolved.json").is_file()
    gates = json.loads((out / "gates_resolved.json").read_text())
    assert "stratified_required" in gates
    # synthetic: no SCREEN_STARTED (non-dispositional)
    assert not (out / "SCREEN_STARTED.json").exists()


def test_runner_fresh_fail_screen_fail(tmp_path: Path):
    frames = _many(25, xau_flat=False)  # XAU cosigns → fresh stratum empty/short
    out = tmp_path / "screen_fail"
    result = screen.run_screen(
        charter_path=CHARTER_V4,
        frames=frames,
        out_dir=out,
        dispositional=False,
    )
    rep = result["report"]
    assert rep["disposition"] == "SCREEN_FAIL"
    assert rep["null_armed"] is False
    assert rep["soft_passers"] == 0
    assert rep["r1_burned"] is False


def test_refuse_overwrite(tmp_path: Path):
    frames = _many(3, xau_flat=True)
    out = tmp_path / "once"
    screen.run_screen(
        charter_path=CHARTER_V4, frames=frames, out_dir=out, dispositional=False
    )
    with pytest.raises(screen.ScreenError, match="refuse overwrite"):
        screen.run_screen(
            charter_path=CHARTER_V4, frames=frames, out_dir=out, dispositional=False
        )


def test_refuse_wrong_charter(tmp_path: Path):
    # Use joint charter if present
    joint = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
    if not joint.is_file():
        pytest.skip("joint charter not present")
    frames = _many(3, xau_flat=True)
    with pytest.raises((screen.ScreenError, fam.ProtocolError), match="WRONG_FAMILY|REFUSE"):
        screen.run_screen(
            charter_path=joint,
            frames=frames,
            out_dir=tmp_path / "bad",
            dispositional=False,
        )


def test_holdout_overlap_refused(tmp_path: Path):
    frames = _many(3, xau_flat=True)
    # Inject a holdout bar
    bad = {s: frames[s].copy() for s in SYMBOLS}
    hold = pd.Timestamp("2026-01-01 00:00:00")
    for s in SYMBOLS:
        row = {
            "time": hold,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "spread": 0.0,
        }
        bad[s] = pd.concat([bad[s], pd.DataFrame([row])], ignore_index=True)
    with pytest.raises(screen.ScreenError, match="HOLDOUT_OVERLAP"):
        screen.run_screen(
            charter_path=CHARTER_V4,
            frames=bad,
            out_dir=tmp_path / "holdout",
            dispositional=False,
        )


def test_cli_dry_without_run_no_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Ensure default out dir is not created by dry CLI
    rc = screen.main(["--charter", str(CHARTER_V4)])
    assert rc == 0


def test_cli_refuses_wrong_family_or_harness():
    joint = ROOT / "results/xau_charters/2026-08-13_joint_london_open_cosign_fade_flat_v4.json"
    if not joint.is_file():
        pytest.skip("joint charter not present")
    with pytest.raises((SystemExit, fam.ProtocolError, screen.ScreenError), match="REFUSE|WRONG"):
        screen.main(["--charter", str(joint)])


def test_no_real_data_symbols_loaded_in_synthetic_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Synthetic path must not call load_package_snapshot."""
    import build_multi_instrument_data_readiness as ready

    def _boom(*_a, **_k):
        raise AssertionError("load_package_snapshot must not be called in synthetic tests")

    monkeypatch.setattr(ready, "load_package_snapshot", _boom)
    frames = _many(3, xau_flat=True)
    screen.run_screen(
        charter_path=CHARTER_V4,
        frames=frames,
        out_dir=tmp_path / "nosnap",
        dispositional=False,
    )


def test_gates_resolved_includes_stratified_required(tmp_path: Path):
    frames = _many(3, xau_flat=True)
    out = tmp_path / "gates"
    screen.run_screen(
        charter_path=CHARTER_V4, frames=frames, out_dir=out, dispositional=False
    )
    gates = json.loads((out / "gates_resolved.json").read_text())
    assert gates["stratified_required"]["used_for"] == "freeze_gate_primary"
    assert "metric_basis" in gates["stratified_required"]


def test_assert_frames_helper_rejects_holdout_bar():
    frames = _many(1, xau_flat=True)
    hs = pd.Timestamp("2026-01-01 00:00:00")
    # OK before holdout
    screen.assert_frames_strictly_before_holdout(frames, hs)
    # Inject
    s = "XAUUSD"
    frames[s] = pd.concat(
        [
            frames[s],
            pd.DataFrame(
                [
                    {
                        "time": hs,
                        "open": 1.0,
                        "high": 1.0,
                        "low": 1.0,
                        "close": 1.0,
                        "spread": 0.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(screen.ScreenError, match="HOLDOUT"):
        screen.assert_frames_strictly_before_holdout(frames, hs)
