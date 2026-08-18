"""Synthetic fixtures for exog_london_fx_cosign_xau_follow_flat (charter v4).

Phase D only — no develop package, no screen, no null, no sealed cycle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import xau_family_exog_london_fx_cosign_xau_follow_flat as fam  # noqa: E402
from xau_charter_protocol import (  # noqa: E402
    validate_charter,
    validate_exogenous_predictor_charter,
)
from xau_exogenous_predictor_core import admit_and_simulate_real, day_ids_from_times  # noqa: E402

CHARTER_V4 = ROOT / "results/xau_charters/2026-08-15_exog_london_fx_cosign_xau_follow_flat_v4.json"
V4_SHA = "3dec09efeee0bc11723c93c0e8ed1de683ac6179c176986cd8d4ba53e594edf5"
SYMBOLS = ("XAUUSD", "EURUSD", "GBPUSD")


# --- builders -----------------------------------------------------------------


def _bars(
    day: str,
    hours: list[int],
    *,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    spreads: float = 0.0,
) -> pd.DataFrame:
    rows = []
    for j, h in enumerate(hours):
        rows.append(
            {
                "time": pd.Timestamp(f"{day} {h:02d}:00:00"),
                "open": opens[j],
                "high": highs[j],
                "low": lows[j],
                "close": closes[j],
                "spread": spreads,
            }
        )
    return pd.DataFrame(rows)


def _quiet_day(
    day: str,
    hours: list[int],
    *,
    base: float,
    bar_range: float,
    spreads: float = 0.0,
) -> pd.DataFrame:
    opens = [base] * len(hours)
    closes = [base] * len(hours)
    highs = [base + bar_range] * len(hours)
    lows = [base - bar_range] * len(hours)
    return _bars(day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads)


def _warmup(n_days: int = 5, start: str = "2024-01-02") -> dict[str, pd.DataFrame]:
    bases = {"XAUUSD": 2000.0, "EURUSD": 1.10, "GBPUSD": 1.25}
    ranges = {"XAUUSD": 3.0, "EURUSD": 0.0015, "GBPUSD": 0.0015}
    hours = list(range(1, 21))
    start_ts = pd.Timestamp(start)
    parts: dict[str, list[pd.DataFrame]] = {s: [] for s in SYMBOLS}
    for d in range(n_days):
        day = (start_ts + pd.DateOffset(days=int(d))).strftime("%Y-%m-%d")
        for s in SYMBOLS:
            parts[s].append(
                _quiet_day(day, hours, base=bases[s], bar_range=ranges[s], spreads=0.0)
            )
    return {s: pd.concat(parts[s], ignore_index=True) for s in SYMBOLS}


def _signal_day(
    day: str,
    *,
    fx: str = "up",
    xau_tstar: str = "flat",
    t_star_hour: int = 7,
    hours: list[int] | None = None,
    post: str = "tp_follow",
    spreads: float = 0.0,
) -> dict[str, pd.DataFrame]:
    """One calendar day on hours default 1..14 (enough for H=3 after hour 7).

    fx: 'up' | 'down' | 'disagree' | 'zero_eur' | 'zero_gbp'
    xau_tstar: 'flat' | 'up' | 'down'  (reporting only; must not affect admission)
    post: 'tp_follow' | 'flat' | 'sl_against'
    """
    if hours is None:
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
            if h == t_star_hour:
                if s in ("EURUSD", "GBPUSD"):
                    if fx == "up":
                        c = base + scale
                    elif fx == "down":
                        c = base - scale
                    elif fx == "disagree":
                        c = base + scale if s == "EURUSD" else base - scale
                    elif fx == "zero_eur" and s == "EURUSD":
                        c = base
                    elif fx == "zero_eur" and s == "GBPUSD":
                        c = base + scale
                    elif fx == "zero_gbp" and s == "GBPUSD":
                        c = base
                    elif fx == "zero_gbp" and s == "EURUSD":
                        c = base + scale
                else:  # XAU at T* — reporting label only
                    if xau_tstar == "up":
                        c = base + scale
                    elif xau_tstar == "down":
                        c = base - scale
                    else:
                        c = base
            elif h >= t_star_hour + 1:
                # hold window path on XAU; predictors quiet
                if s == "XAUUSD":
                    o = base
                    if post == "tp_follow":
                        # long follow needs up path; short follow needs down path
                        direction = 1 if fx in ("up", "zero_eur", "zero_gbp") else -1
                        if fx == "down":
                            direction = -1
                        if fx == "up":
                            direction = 1
                        # After entry, push toward TP
                        step = (h - t_star_hour) * scale * 8
                        c = base + direction * step
                    elif post == "sl_against":
                        direction = 1 if fx == "up" else -1
                        c = base - direction * scale * 20
                    else:
                        c = base
                else:
                    o = base
                    c = base
            hi = max(o, c) + scale * 0.5
            lo = min(o, c) - scale * 0.5
            if s == "XAUUSD" and h >= t_star_hour + 1 and post == "tp_follow":
                # Widen so TP is reachable within H given ATR
                direction = 1 if fx == "up" else -1
                if fx == "down":
                    direction = -1
                if direction > 0:
                    hi = max(hi, base + scale * 40)
                else:
                    lo = min(lo, base - scale * 40)
            if s == "XAUUSD" and h >= t_star_hour + 1 and post == "sl_against":
                direction = 1 if fx == "up" else -1
                if direction > 0:
                    lo = min(lo, base - scale * 40)
                else:
                    hi = max(hi, base + scale * 40)
            opens.append(o)
            highs.append(hi)
            lows.append(lo)
            closes.append(c)
        out[s] = _bars(
            day, hours, opens=opens, highs=highs, lows=lows, closes=closes, spreads=spreads
        )
    return out


def _merge(signal: dict[str, pd.DataFrame], warm: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    w = warm if warm is not None else _warmup()
    return {s: pd.concat([w[s], signal[s]], ignore_index=True) for s in SYMBOLS}


def _many_signal_days(
    n: int,
    *,
    fx: str = "up",
    xau_tstar: str = "flat",
    post: str = "tp_follow",
    start: str = "2024-02-01",
) -> dict[str, pd.DataFrame]:
    warm = _warmup(5, start="2024-01-02")
    start_ts = pd.Timestamp(start)
    frames = {s: [warm[s]] for s in SYMBOLS}
    for i in range(n):
        day = (start_ts + pd.DateOffset(days=int(i))).strftime("%Y-%m-%d")
        # skip weekends roughly by using consecutive calendar days; H1 synthetic ok
        sig = _signal_day(day, fx=fx, xau_tstar=xau_tstar, post=post)
        for s in SYMBOLS:
            frames[s].append(sig[s])
    return {s: pd.concat(frames[s], ignore_index=True) for s in SYMBOLS}


def _charter() -> dict:
    return json.loads(CHARTER_V4.read_text())


# --- charter binding ----------------------------------------------------------


def test_charter_v4_sha_and_validators():
    assert hashlib.sha256(CHARTER_V4.read_bytes()).hexdigest() == V4_SHA
    ch = fam.load_charter(CHARTER_V4)
    assert ch["family_id"] == fam.FAMILY_ID
    assert ch["charter_version"] == 4
    assert validate_charter(ch) == []
    assert validate_exogenous_predictor_charter(ch) == []


def test_module_dd_convention_matches_charter_metric_basis():
    ch = _charter()
    mb = ch["gates"]["stratified_required"]["metric_basis"]
    assert mb["stratum_dd_method"] == fam.STRATUM_DD_CONVENTION
    assert mb["n_trades_min_applies_to_stratum"] is True


def test_refuses_wrong_family_not_frozen_wrong_harness():
    ch = _charter()
    bad = copy.deepcopy(ch)
    bad["family_id"] = "someone_else"
    with pytest.raises(fam.ProtocolError, match="REFUSE_WRONG_FAMILY"):
        fam.assert_family_charter(bad)
    bad2 = copy.deepcopy(ch)
    bad2["status"] = "DRAFT"
    with pytest.raises(fam.ProtocolError, match="REFUSE_NOT_FROZEN"):
        fam.assert_family_charter(bad2)
    bad3 = copy.deepcopy(ch)
    bad3["harness"] = dict(ch["harness"])
    bad3["harness"]["kind"] = "multi_instrument_joint_v1"
    with pytest.raises(fam.ProtocolError, match="REFUSE_WRONG_HARNESS"):
        fam.assert_family_charter(bad3)


def test_grid_cardinality_one_zero_free_knobs():
    ch = _charter()
    assert ch["n_free_knobs"] == 0
    assert ch["free_knobs"] == []
    assert ch["search_cardinality"] == 1
    g = fam.build_grid()
    assert len(g) == 1
    assert fam.grid() == g


def test_not_registered_as_null_maxstat_builtin():
    from xau_family_null_maxstat import BUILTINS, load_family

    assert "exog_london_fx_cosign_xau_follow_flat" not in BUILTINS
    plug = load_family("exog_london_fx_cosign_xau_follow_flat")
    with pytest.raises(RuntimeError, match="REFUSE_SINGLE_FRAME_SIMULATE"):
        plug.simulate(
            pd.DataFrame(
                {
                    "time": [pd.Timestamp("2024-01-01 07:00:00")],
                    "open": [1.0],
                    "high": [1.0],
                    "low": [1.0],
                    "close": [1.0],
                }
            )
        )


def test_refuses_each_prohibited_runner():
    ch = _charter()
    runners = list(ch["harness"]["prohibited_runners"])
    assert runners
    for r in runners:
        with pytest.raises(fam.ProtocolError, match="REFUSE_PROHIBITED_RUNNER"):
            fam.refuse_prohibited_runner(r, ch)
        with pytest.raises(fam.ProtocolError, match="REFUSE_PROHIBITED_RUNNER"):
            fam.refuse_prohibited_runner(Path(r).name, ch)


# --- signal predicate ---------------------------------------------------------


def test_fx_up_cosign_long_entry_at_tstar_plus_1_open():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="flat", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    assert len(res.real.events) == 1
    ev = res.real.events[0]
    assert ev.side == 1
    tr = res.real.trades[0]
    assert tr.entry_idx == ev.t_entry_idx
    assert tr.entry_idx == ev.t_star_idx + 1
    xau = res.frames_on_i["XAUUSD"]
    assert tr.entry_price == pytest.approx(float(xau["open"].iloc[ev.t_entry_idx]))


def test_fx_down_cosign_short():
    frames = _merge(_signal_day("2024-02-01", fx="down", xau_tstar="flat", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    assert len(res.real.events) == 1
    assert res.real.events[0].side == -1


def test_disagreeing_signs_no_event():
    frames = _merge(_signal_day("2024-02-01", fx="disagree"))
    res = fam.run_family(frames, charter=_charter())
    assert res.real.events == []
    assert res.real.trades == []


def test_zero_leg_no_event():
    for fx in ("zero_eur", "zero_gbp"):
        frames = _merge(_signal_day("2024-02-01", fx=fx))
        res = fam.run_family(frames, charter=_charter())
        assert res.real.events == [], fx


def test_tstar_is_earliest_hour_among_7_8_9():
    hours = [6, 7, 8, 9, 10, 11, 12, 13]
    frames = _merge(
        _signal_day("2024-02-01", fx="up", hours=hours, t_star_hour=7, post="flat")
    )
    res = fam.run_family(frames, charter=_charter())
    assert len(res.real.events) == 1
    xau = res.frames_on_i["XAUUSD"]
    t_star = int(res.real.events[0].t_star_idx)
    assert int(xau["hour"].iloc[t_star]) == 7
    # only one nonzero signal side
    assert int(np.count_nonzero(res.signal_sides)) == 1


def test_day_without_hours_789_no_candidate():
    hours = [1, 2, 3, 4, 5, 6, 10, 11, 12]
    frames = _merge(
        _signal_day("2024-02-01", fx="up", hours=hours, t_star_hour=10, post="flat")
    )
    # t_star_hour=10 is outside {7,8,9}; builder still puts fx move at 10 but
    # family must ignore it
    res = fam.run_family(frames, charter=_charter())
    assert res.real.events == []


def test_xau_tstar_flip_does_not_affect_admission():
    snaps = []
    for xau_tstar in ("up", "down", "flat"):
        frames = _merge(
            _signal_day("2024-02-01", fx="up", xau_tstar=xau_tstar, post="flat")
        )
        res = fam.run_family(frames, charter=_charter())
        snaps.append(
            (
                [e.side for e in res.real.events],
                [e.t_star_idx for e in res.real.events],
                [e.t_entry_idx for e in res.real.events],
                [t.entry_price for t in res.real.trades],
                [t.side for t in res.real.trades],
                res.signal_sides.copy(),
            )
        )
    assert snaps[0][0] == snaps[1][0] == snaps[2][0]
    assert snaps[0][1] == snaps[1][1] == snaps[2][1]
    assert snaps[0][2] == snaps[1][2] == snaps[2][2]
    assert snaps[0][3] == snaps[1][3] == snaps[2][3]
    assert snaps[0][4] == snaps[1][4] == snaps[2][4]
    assert np.array_equal(snaps[0][5], snaps[1][5])
    assert np.array_equal(snaps[0][5], snaps[2][5])


# --- causality ----------------------------------------------------------------


def test_atr_anchored_at_tstar_not_entry_bar():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    res1 = fam.run_family(frames, charter=_charter())
    assert len(res1.real.events) == 1
    atr1 = float(res1.real.events[0].atr_tstar)
    entry = int(res1.real.events[0].t_entry_idx)
    # Mutate entry bar high/low on I; ATR at T* must be unchanged
    aligned = fam.align_intersection(frames)
    aligned["XAUUSD"] = aligned["XAUUSD"].copy()
    aligned["XAUUSD"].loc[aligned["XAUUSD"].index[entry], "high"] = 5000.0
    aligned["XAUUSD"].loc[aligned["XAUUSD"].index[entry], "low"] = 100.0
    res2 = fam.run_family(aligned, charter=_charter(), already_aligned=True)
    assert len(res2.real.events) == 1
    atr2 = float(res2.real.events[0].atr_tstar)
    assert atr2 == pytest.approx(atr1)
    # SL distance from entry uses atr_tstar
    ch = _charter()
    sl_atr = float(ch["rule"]["sl_atr_fixed"])
    e1, e2 = res1.real.events[0], res2.real.events[0]
    assert abs(e1.atr_tstar * sl_atr - e2.atr_tstar * sl_atr) < 1e-12


def test_no_exit_uses_tstar_bar_range():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="tp_follow"))
    aligned = fam.align_intersection(frames)
    res = fam.run_family(aligned, charter=_charter(), already_aligned=True)
    assert res.real.trades
    t_star = int(res.real.events[0].t_star_idx)
    for tr in res.real.trades:
        assert tr.exit_idx != t_star
        assert tr.entry_idx > t_star


def test_missing_tstar_plus_1_on_intersection_no_trade():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    # Drop all post-T* bars from EUR so I has T* but no T*+1.. hold window
    eur = frames["EURUSD"]
    frames["EURUSD"] = eur.loc[
        eur["time"] < pd.Timestamp("2024-02-01 08:00:00")
    ].reset_index(drop=True)
    res = fam.run_family(frames, charter=_charter())
    # T* may still be on I, but admit requires T*+1 .. T*+H-1 on I
    assert res.real.trades == []
    assert res.real.events == []


def test_entry_at_open_of_tstar_plus_1():
    # Distinct T* close vs T*+1 open so we can prove entry uses the latter
    sig = _signal_day("2024-02-01", fx="up", xau_tstar="up", post="flat")
    # Force T*+1 open to a distinct level on XAU
    xau = sig["XAUUSD"]
    row8 = xau["time"] == pd.Timestamp("2024-02-01 08:00:00")
    sig["XAUUSD"] = xau.copy()
    sig["XAUUSD"].loc[row8, "open"] = 2010.0
    sig["XAUUSD"].loc[row8, "high"] = 2011.0
    sig["XAUUSD"].loc[row8, "low"] = 2009.0
    sig["XAUUSD"].loc[row8, "close"] = 2010.0
    frames = _merge(sig)
    res = fam.run_family(frames, charter=_charter())
    ev = res.real.events[0]
    tr = res.real.trades[0]
    xau_i = res.frames_on_i["XAUUSD"]
    assert tr.entry_idx == ev.t_star_idx + 1
    assert tr.entry_price == pytest.approx(float(xau_i.iloc[ev.t_entry_idx]["open"]))
    assert tr.entry_price == pytest.approx(2010.0)
    assert tr.entry_price != pytest.approx(float(xau_i.iloc[ev.t_star_idx]["open"]))
    assert tr.entry_price != pytest.approx(float(xau_i.iloc[ev.t_star_idx]["close"]))


# --- calendar / occupancy / costs ---------------------------------------------


def test_intersection_excludes_timestamp_missing_from_one_symbol():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    # Remove an early warmup hour from GBP only
    gbp = frames["GBPUSD"]
    t0 = gbp["time"].iloc[0]
    frames["GBPUSD"] = gbp.loc[gbp["time"] != t0].reset_index(drop=True)
    aligned = fam.align_intersection(frames)
    assert t0 not in set(aligned["XAUUSD"]["time"].tolist())
    assert len(aligned["XAUUSD"]) == len(aligned["EURUSD"]) == len(aligned["GBPUSD"])


def test_already_aligned_shifted_predictor_timestamps_refused():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    aligned = fam.align_intersection(frames)
    bad = {s: aligned[s].copy() for s in SYMBOLS}
    bad["EURUSD"]["time"] = bad["EURUSD"]["time"] + pd.Timedelta(hours=1)
    with pytest.raises(fam.ProtocolError, match="timestamp|misaligned|identical|shifted"):
        fam.run_family(bad, charter=_charter(), already_aligned=True)


def test_empty_intersection_refuses():
    frames = {
        "XAUUSD": _quiet_day("2024-02-01", [7, 8, 9], base=2000.0, bar_range=1.0),
        "EURUSD": _quiet_day("2024-02-02", [7, 8, 9], base=1.1, bar_range=0.001),
        "GBPUSD": _quiet_day("2024-02-03", [7, 8, 9], base=1.25, bar_range=0.001),
    }
    with pytest.raises(fam.EmptyIntersectionError):
        fam.align_intersection(frames)


def test_tz_aware_server_time_refuses():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    for s in SYMBOLS:
        frames[s] = frames[s].copy()
        frames[s]["time"] = pd.to_datetime(frames[s]["time"], utc=True)
    with pytest.raises(fam.ProtocolError, match="timezone-naive|server_clock"):
        fam.run_family(frames, charter=_charter())


def test_same_day_hold_rejects_crossing_day_boundary():
    # T* at hour 22 with only bars through 23 → cannot fit H=3 same day
    hours = [20, 21, 22, 23]
    frames = _merge(
        _signal_day("2024-02-01", fx="up", hours=hours, t_star_hour=22, post="flat")
    )
    res = fam.run_family(frames, charter=_charter())
    assert res.real.events == []
    assert res.real.trades == []


def test_fixed_h_occupancy_second_candidate_skipped():
    """Occupancy is Phase B behaviour the family relies on — probe via core."""
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    aligned = fam.align_intersection(frames)
    xau = aligned["XAUUSD"]
    n = len(xau)
    sides = np.zeros(n, dtype=np.int64)
    # Find a mid index with room for two H=3 windows that overlap
    # Put signals at i and i+1 (entries i+1 and i+2 → overlap)
    # Need same day_id across windows
    day_id = day_ids_from_times(xau["time"])
    # pick an index on signal day hour 7 area
    hours = xau["hour"].to_numpy(int)
    candidates = np.flatnonzero((hours == 7) | (hours == 8))
    assert len(candidates) >= 2
    i0 = int(candidates[-2])
    i1 = int(candidates[-1])
    sides[i0] = 1
    sides[i1] = 1
    ch = _charter()
    p = fam._params_from_charter(ch)
    real = admit_and_simulate_real(
        open_=xau["open"].to_numpy(float),
        high=xau["high"].to_numpy(float),
        low=xau["low"].to_numpy(float),
        close=xau["close"].to_numpy(float),
        spread=xau["spread"].to_numpy(float),
        day_id=day_id,
        signal_sides=sides,
        sl_atr=p["sl_atr"],
        tp_atr=p["tp_atr"],
        risk_pct=p["risk_pct"],
        lot_min=p["lot_min"],
        lot_step=p["lot_step"],
        lot_max=p["lot_max"],
        contract_size=p["contract_size"],
        point_size=p["point_size"],
        commission_per_lot=p["commission_per_lot"],
        slippage_points=p["slippage_points"],
        start_balance=p["start_balance"],
        h=p["h"],
        atr_period=p["atr_period"],
    )
    assert len(real.events) == 1


@pytest.mark.parametrize(
    "bad",
    ["missing", "nan", "inf", "neg"],
)
def test_spread_fail_closed(bad: str):
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    if bad == "missing":
        frames["XAUUSD"] = frames["XAUUSD"].drop(columns=["spread"])
        with pytest.raises(fam.ProtocolError, match="spread"):
            fam.run_family(frames, charter=_charter())
        return
    frames["XAUUSD"] = frames["XAUUSD"].copy()
    if bad == "nan":
        frames["XAUUSD"].loc[frames["XAUUSD"].index[0], "spread"] = float("nan")
    elif bad == "inf":
        frames["XAUUSD"].loc[frames["XAUUSD"].index[0], "spread"] = float("inf")
    else:
        frames["XAUUSD"].loc[frames["XAUUSD"].index[0], "spread"] = -1.0
    with pytest.raises(fam.ProtocolError, match="spread|NaN|Inf|negative|non-finite"):
        fam.run_family(frames, charter=_charter())


def test_lot_floor_step_min_max_xau_meta():
    frames = _merge(_signal_day("2024-02-01", fx="up", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    ch = _charter()
    lot_min = float(ch["fixed"]["lot_min"])
    lot_step = float(ch["fixed"]["lot_step"])
    lot_max = float(ch["fixed"]["lot_max"])
    meta = ch["instrument"]["per_symbol_meta"]["XAUUSD"]
    assert float(meta["point_size"]) == pytest.approx(0.01)
    assert float(meta["contract_size"]) == pytest.approx(100.0)
    assert res.real.events
    for ev in res.real.events:
        assert ev.lots >= lot_min - 1e-15
        assert ev.lots <= lot_max + 1e-15
        steps = ev.lots / lot_step
        assert abs(steps - round(steps)) < 1e-9


# --- stratified gate ----------------------------------------------------------


def test_stratum_zero_return_is_not_cosign():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="flat", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    assert res.real.events
    assert res.stratified.event_stratum[res.real.events[0].event_id] == fam.STRATUM_NOT_COSIGN


def test_stratum_opposite_sign_is_not_cosign():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="down", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    assert res.stratified.event_stratum[res.real.events[0].event_id] == fam.STRATUM_NOT_COSIGN


def test_stratum_same_sign_nonzero_is_cosign():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="up", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    assert res.stratified.event_stratum[res.real.events[0].event_id] == fam.STRATUM_COSIGN


def test_pooled_and_fresh_pass_one_soft_passer():
    # >=20 NOT_COSIGN profitable trades (XAU T* flat)
    frames = _many_signal_days(25, fx="up", xau_tstar="flat", post="tp_follow")
    res = fam.run_family(frames, charter=_charter())
    st = res.stratified
    n_fresh = int(st.by_stratum[fam.STRATUM_NOT_COSIGN]["n_trades"])
    assert n_fresh >= 20
    assert st.soft_pass_pooled is True
    assert st.soft_pass_fresh is True
    assert st.soft_passers == 1
    assert st.disposition == "SOFT_PASS"
    assert st.null_armed is True
    assert st.r1_burned is False


def test_pooled_pass_fresh_fail_is_screen_fail_not_passer():
    # Many COSIGN winners; zero NOT_COSIGN → fresh fails n_min; pooled can pass
    frames = _many_signal_days(25, fx="up", xau_tstar="up", post="tp_follow")
    res = fam.run_family(frames, charter=_charter())
    st = res.stratified
    assert int(st.pooled["n_trades"]) >= 20
    assert st.soft_pass_pooled is True
    assert st.soft_pass_fresh is False
    assert st.soft_passers == 0
    assert st.disposition == "SCREEN_FAIL"
    assert st.null_armed is False
    assert st.r1_burned is False
    # must not be reported as a passer
    rep = fam.report_dict(res)
    assert rep["soft_passers"] == 0
    assert rep["disposition"] == "SCREEN_FAIL"


def test_unlabelled_event_raises():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="flat", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    real = res.real
    # Corrupt: trade with unknown event_id
    bad_trades = list(real.trades)
    t0 = bad_trades[0]
    bad_trades[0] = fam.TradeResult(
        event_id=99999,
        entry_idx=t0.entry_idx,
        exit_idx=t0.exit_idx,
        side=t0.side,
        lots=t0.lots,
        entry_price=t0.entry_price,
        exit_price=t0.exit_price,
        exit_reason=t0.exit_reason,
        pnl=t0.pnl,
    )
    real.trades = bad_trades
    xau = res.frames_on_i["XAUUSD"]
    with pytest.raises(fam.StratifiedEvaluationError, match="stratum|label|unlabelled|event_id"):
        fam.evaluate_stratified(
            real,
            open_=xau["open"].to_numpy(float),
            close=xau["close"].to_numpy(float),
            soft=_charter()["gates"]["soft"],
            start_balance=float(_charter()["fixed"]["start_balance"]),
        )


def test_blank_stratified_evaluation_raises():
    with pytest.raises(fam.StratifiedEvaluationError, match="absent|None"):
        fam.evaluate_stratified(
            None,  # type: ignore[arg-type]
            open_=np.array([1.0]),
            close=np.array([1.0]),
            soft=_charter()["gates"]["soft"],
            start_balance=float(_charter()["fixed"]["start_balance"]),
        )


def test_report_emits_pooled_and_both_strata_metrics():
    frames = _merge(_signal_day("2024-02-01", fx="up", xau_tstar="flat", post="flat"))
    res = fam.run_family(frames, charter=_charter())
    rep = fam.report_dict(res)
    for key in ("n", "profit_factor", "net_profit", "max_drawdown_pct"):
        assert key in rep["pooled"]
        assert key in rep["strata"][fam.STRATUM_COSIGN]
        assert key in rep["strata"][fam.STRATUM_NOT_COSIGN]
    assert rep["dd_convention"] == fam.STRATUM_DD_CONVENTION
    assert res.stratified.event_stratum
