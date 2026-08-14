#!/usr/bin/env python3
"""MQL5 ↔ Python parity for HTF Fib buffers, pivots, and Wilder ATR.

The committed synthetic fixture is a frozen golden master: changing
``htf_fib_core`` without regenerating it fails ``verify_fixture``. That does
**not** prove the numbers originally came from MQL5. Hand-derived planted
pivots / fib levels / ATR seed (``PLANTED_*``, ``FIB_*``) are the independent
check. ``--write-synthetic`` is a schema-migration guard (byte-match).

Same-TF: fib live at ``i >= confirm_idx`` (confirm bar included; forming bar
signal 0 via shift 1). MTF: chart row eligible when
``chart_bar_close >= htf_confirm_open + htf_period``.

SAFETY: read-only. Never places orders. ForexSignalLogger is not declared
live-safe — the HTF scan used to treat the forming bar as a confirm wing.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from htf_fib_core import (  # noqa: E402
    confirmed_pivots_with_centers,
    expand_fib_states,
    walk_swing_and_fibs,
    wilder_atr,
)

SCHEMA = "mql5-python-parity/v1"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "mql5_parity" / "htf_fib_h1_synthetic"

# Authoritative iCustom map for ForexHtfPivotsFib v1.42+ (SetIndexBuffer).
# mql5/README.md historically listed signal as 7 — that table is stale.
HTF_FIB_BUFFERS: dict[int, str] = {
    0: "ema_fast",
    1: "ema_slow",
    2: "ema_bias",
    3: "long_arrow",
    4: "short_arrow",
    5: "fib_618",
    6: "fib_786",
    7: "swing_dir",
    8: "signal",
    9: "rsi",
    10: "rsi_ma",
}
SIGNAL_BUFFER = 8
SWING_DIR_BUFFER = 7
SIGNAL_SHIFT = 1  # last closed bar; forming bar must stay 0
ATR_PERIOD = 14

# Hand-derived planted geometry (independent of htf_fib_core).
PLANTED_LOW_CENTER = 20
PLANTED_HIGH_CENTER = 40
PLANTED_RIGHT = 5
PLANTED_CONFIRM_LOW = PLANTED_LOW_CENTER + PLANTED_RIGHT  # 25
PLANTED_CONFIRM_HIGH = PLANTED_HIGH_CENTER + PLANTED_RIGHT  # 45
PLANTED_LOW_PRICE = 90.0
PLANTED_HIGH_PRICE = 120.0
# Same-TF: fib may be live on the confirmation bar (consumed via shift 1).
FIB_LIVE_FROM = PLANTED_CONFIRM_HIGH  # 45
FIB_618 = PLANTED_HIGH_PRICE - (PLANTED_HIGH_PRICE - PLANTED_LOW_PRICE) * 0.618
FIB_786 = PLANTED_HIGH_PRICE - (PLANTED_HIGH_PRICE - PLANTED_LOW_PRICE) * 0.786
# 120 - 30*0.618 = 101.46; 120 - 30*0.786 = 96.42
ABS_TOL_MAX = 1e-3
REQUIRED_MANIFEST_INTS = (
    "left",
    "right",
    "atr_period",
    "compare_from_chart_idx",
    "n_bars",
    "n_htf_bars",
)
REQUIRED_MANIFEST_STRS = ("chart_tf", "htf_tf")
TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
    "MN1": 2592000,
}


class ParityError(Exception):
    """One or more parity checks failed."""


@dataclass
class CopyStat:
    requested: int
    copied: int

    @property
    def ok(self) -> bool:
        return self.copied > 0 and self.copied >= self.requested


@dataclass
class Fixture:
    path: Path
    manifest: dict[str, Any]
    times: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    atr14: np.ndarray
    fib_618: np.ndarray
    fib_786: np.ndarray
    swing_dir: np.ndarray
    signal: np.ndarray
    pivots: list[dict[str, Any]]
    htf_high: np.ndarray
    htf_low: np.ndarray
    htf_times: list[str]
    copy: dict[str, CopyStat] = field(default_factory=dict)


def parse_bar_time(raw: str) -> datetime:
    """Accept MQL5 ``2024.01.02 00:00:00`` and ISO ``2024-01-02 00:00:00``."""
    text = raw.strip()
    if not text:
        raise ValueError("empty timestamp")
    if text[4:5] == ".":
        date, _, rest = text.partition(" ")
        text = date.replace(".", "-") + ((" " + rest) if rest else "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized timestamp: {raw!r}")


def format_mql_time(dt: datetime) -> str:
    return dt.strftime("%Y.%m.%d %H:%M:%S")


def _f(row: dict[str, str], key: str) -> float:
    raw = (row.get(key) or "").strip()
    if raw == "" or raw.lower() in {"nan", "empty"}:
        return float("nan")
    return float(raw)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise ParityError(f"missing fixture file: {path}")
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _copy_stat(raw: Any) -> CopyStat:
    if isinstance(raw, dict):
        return CopyStat(int(raw.get("requested", 0)), int(raw.get("copied", 0)))
    raise ParityError(f"copy stat must be an object, got {type(raw).__name__}")


def tf_seconds(name: str) -> int:
    key = str(name).replace("PERIOD_", "").strip()
    if key not in TF_SECONDS:
        raise ParityError(f"unknown timeframe {name!r}")
    return TF_SECONDS[key]


def expected_fib_source(htf_tf: str) -> int:
    """Map scan HTF to the indicator's fib_source (0=H4, 1=D1)."""
    key = str(htf_tf).replace("PERIOD_", "").strip()
    if key == "H4":
        return 0
    if key == "D1":
        return 1
    raise ParityError(f"cannot map htf_tf={htf_tf!r} to fib_source")


def _require_indicator_pin(manifest: dict[str, Any]) -> None:
    """Live dumps must prove iCustom ran the same left/right/source as the scan."""
    if manifest.get("source") != "mql5_export":
        return
    for key in ("indicator_left", "indicator_right", "indicator_fib_source"):
        if key not in manifest:
            raise ParityError(
                f"manifest.{key} is required for mql5_export "
                "(indicator sidecar missing — dump is not pinned to the "
                "indicator configuration)"
            )
    if not str(manifest.get("indicator_version") or "").strip():
        raise ParityError(
            "manifest.indicator_version is required for mql5_export "
            "(sidecar version missing — dump is not pinned to HTF_FIB_VER)"
        )
    left = int(manifest["left"])
    right = int(manifest["right"])
    ind_left = int(manifest["indicator_left"])
    ind_right = int(manifest["indicator_right"])
    ind_src = int(manifest["indicator_fib_source"])
    if ind_left != left or ind_right != right:
        raise ParityError(
            f"indicator left/right {ind_left}/{ind_right} != "
            f"scan left/right {left}/{right}"
        )
    expect_src = expected_fib_source(str(manifest["htf_tf"]))
    if ind_src != expect_src:
        raise ParityError(
            f"indicator_fib_source={ind_src} != expected {expect_src} "
            f"for htf_tf={manifest['htf_tf']}"
        )


def _require_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("export_ok") is not True:
        raise ParityError(
            f"export_ok must be true, got {manifest.get('export_ok')!r} "
            f"error={manifest.get('export_error')}"
        )
    for key in REQUIRED_MANIFEST_INTS:
        if key not in manifest:
            raise ParityError(f"manifest.{key} is required")
        int(manifest[key])
    for key in REQUIRED_MANIFEST_STRS:
        if not str(manifest.get(key) or "").strip():
            raise ParityError(f"manifest.{key} is required")
    if "abs_tol" not in manifest:
        raise ParityError("manifest.abs_tol is required")
    abs_tol = float(manifest["abs_tol"])
    if not math.isfinite(abs_tol) or abs_tol <= 0 or abs_tol > ABS_TOL_MAX:
        raise ParityError(
            f"manifest.abs_tol={abs_tol!r} must be finite, > 0, and <= {ABS_TOL_MAX}"
        )
    _require_indicator_pin(manifest)


def load_fixture(path: Path) -> Fixture:
    path = path.resolve()
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise ParityError(f"missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise ParityError(
            f"unsupported schema {manifest.get('schema')!r} (need {SCHEMA})"
        )
    _require_manifest(manifest)

    bars = _read_csv(path / "bars.csv")
    buffers = _read_csv(path / "buffers.csv")
    pivots = _read_csv(path / "pivots.csv")
    if len(bars) == 0:
        raise ParityError("bars.csv is empty")
    if len(bars) != len(buffers):
        raise ParityError(
            f"bars.csv rows={len(bars)} != buffers.csv rows={len(buffers)}"
        )
    for i, (b, u) in enumerate(zip(bars, buffers, strict=True)):
        if b["time"] != u["time"]:
            raise ParityError(
                f"timestamp mismatch at row {i}: bars={b['time']!r} "
                f"buffers={u['time']!r}"
            )

    htf_path = path / "htf_bars.csv"
    if not htf_path.is_file():
        raise ParityError(f"missing {htf_path} — refuse silent HTF=chart alias")
    htf = _read_csv(htf_path)

    copy_raw = manifest.get("copy")
    if not isinstance(copy_raw, dict):
        raise ParityError("manifest.copy is required")
    for key in ("rates", "htf_rates"):
        if key not in copy_raw:
            raise ParityError(f"manifest.copy.{key} is required")
    buffers_copy = copy_raw.get("buffers")
    if not isinstance(buffers_copy, dict):
        raise ParityError("manifest.copy.buffers is required")
    for buf_id in range(11):
        if str(buf_id) not in buffers_copy:
            raise ParityError(f"manifest.copy.buffers.{buf_id} is required")
    copy: dict[str, CopyStat] = {
        "rates": _copy_stat(copy_raw["rates"]),
        "htf_rates": _copy_stat(copy_raw["htf_rates"]),
    }
    for buf_id, stat in buffers_copy.items():
        copy[f"buffer_{buf_id}"] = _copy_stat(stat)

    n_bars = int(manifest["n_bars"])
    n_htf = int(manifest["n_htf_bars"])
    if n_bars != len(bars) or n_bars != len(buffers):
        raise ParityError(
            f"n_bars={n_bars} != len(bars)={len(bars)} or len(buffers)={len(buffers)}"
        )
    if n_htf != len(htf):
        raise ParityError(f"n_htf_bars={n_htf} != len(htf_bars)={len(htf)}")
    if n_bars != copy["rates"].copied:
        raise ParityError(
            f"n_bars={n_bars} != copy.rates.copied={copy['rates'].copied}"
        )
    if n_htf != copy["htf_rates"].copied:
        raise ParityError(
            f"n_htf_bars={n_htf} != copy.htf_rates.copied={copy['htf_rates'].copied}"
        )
    return Fixture(
        path=path,
        manifest=manifest,
        times=[r["time"] for r in bars],
        open=np.array([_f(r, "open") for r in bars], dtype=float),
        high=np.array([_f(r, "high") for r in bars], dtype=float),
        low=np.array([_f(r, "low") for r in bars], dtype=float),
        close=np.array([_f(r, "close") for r in bars], dtype=float),
        atr14=np.array([_f(r, "atr14") for r in buffers], dtype=float),
        fib_618=np.array([_f(r, "fib_618") for r in buffers], dtype=float),
        fib_786=np.array([_f(r, "fib_786") for r in buffers], dtype=float),
        swing_dir=np.array([_f(r, "swing_dir") for r in buffers], dtype=float),
        signal=np.array([_f(r, "signal") for r in buffers], dtype=float),
        pivots=[
            {
                "center_idx": int(r["center_idx"]),
                "confirm_idx": int(r["confirm_idx"]),
                "center_time": r["center_time"],
                "confirm_time": r["confirm_time"],
                "ptype": int(float(r["ptype"])),
                "price": float(r["price"]),
            }
            for r in pivots
        ],
        htf_high=np.array([_f(r, "high") for r in htf], dtype=float),
        htf_low=np.array([_f(r, "low") for r in htf], dtype=float),
        htf_times=[r["time"] for r in htf],
        copy=copy,
    )


def assert_copy_complete(fx: Fixture) -> None:
    """Strict schema: every copy member present and copied == requested."""
    errors: list[str] = []
    for name, stat in fx.copy.items():
        if stat.requested <= 0:
            errors.append(f"{name}: requested={stat.requested} (must be > 0)")
        elif stat.copied != stat.requested:
            errors.append(
                f"{name}: copied={stat.copied} != requested={stat.requested}"
            )
    if errors:
        raise ParityError("partial copy: " + "; ".join(errors))


def assert_buffer_contract(fx: Fixture) -> None:
    raw = fx.manifest.get("buffer_map") or {}
    if not raw:
        raise ParityError("manifest.buffer_map missing")
    got = {int(k): str(v) for k, v in raw.items()}
    if got != HTF_FIB_BUFFERS:
        raise ParityError(
            f"buffer_map drift: fixture={got} expected={HTF_FIB_BUFFERS}"
        )
    if int(fx.manifest.get("signal_buffer", -1)) != SIGNAL_BUFFER:
        raise ParityError(
            f"signal_buffer={fx.manifest.get('signal_buffer')} "
            f"expected {SIGNAL_BUFFER}"
        )
    if int(fx.manifest.get("signal_shift", -1)) != SIGNAL_SHIFT:
        raise ParityError(
            f"signal_shift={fx.manifest.get('signal_shift')} "
            f"expected {SIGNAL_SHIFT} (closed bar)"
        )
    if not fx.manifest.get("closed_bar_only", False):
        raise ParityError("closed_bar_only must be true")


def assert_timestamps_chrono(times: list[str], label: str) -> list[datetime]:
    parsed = [parse_bar_time(t) for t in times]
    for i in range(1, len(parsed)):
        if parsed[i] <= parsed[i - 1]:
            raise ParityError(
                f"{label} not chronological at {i}: {times[i - 1]} -> {times[i]}"
            )
    return parsed


def assert_closed_bar_signal(fx: Fixture) -> None:
    if len(fx.signal) == 0:
        raise ParityError("empty signal series")
    last = fx.signal[-1]
    if not (last == 0 or np.isnan(last)):
        raise ParityError(
            f"forming bar signal must be 0 (closed-bar only), got {last}"
        )


def assert_pivot_confirmation(fx: Fixture) -> None:
    right = int(fx.manifest["right"])
    if not fx.pivots:
        raise ParityError("pivots.csv is empty")
    for p in fx.pivots:
        if p["confirm_idx"] != p["center_idx"] + right:
            raise ParityError(
                f"lookahead/stamp error: confirm_idx={p['confirm_idx']} "
                f"!= center_idx={p['center_idx']} + right={right}"
            )


def _nan_close(a: float, b: float, abs_tol: float) -> bool:
    a_nan = a != a
    b_nan = b != b
    if a_nan and b_nan:
        return True
    if a_nan or b_nan:
        return False
    return abs(a - b) <= abs_tol


def zone_signal(
    close: np.ndarray,
    direction: np.ndarray,
    fib_a: np.ndarray,
    fib_b: np.ndarray,
) -> np.ndarray:
    """Closed-bar golden-zone signal: last (forming) bar forced to 0."""
    n = len(close)
    out = np.zeros(n, dtype=float)
    for i in range(n - 1):  # exclude forming bar
        if direction[i] == 0 or np.isnan(fib_a[i]) or np.isnan(fib_b[i]):
            continue
        lo = min(fib_a[i], fib_b[i])
        hi = max(fib_a[i], fib_b[i])
        if lo <= close[i] <= hi:
            out[i] = float(direction[i])
    return out


def _same_timeframe(fx: Fixture) -> bool:
    chart_tf = str(fx.manifest["chart_tf"])
    htf_tf = str(fx.manifest["htf_tf"])
    n = len(fx.close)
    if chart_tf == htf_tf:
        if len(fx.htf_high) != n:
            raise ParityError(
                f"chart_tf==htf_tf ({chart_tf}) but lengths "
                f"chart={n} htf={len(fx.htf_high)}"
            )
        return True
    if len(fx.htf_high) == n:
        raise ParityError(
            f"chart_tf={chart_tf} htf_tf={htf_tf} but equal bar counts "
            f"({n}); refuse identity expansion"
        )
    return False


def python_side(fx: Fixture) -> dict[str, Any]:
    left = int(fx.manifest["left"])
    right = int(fx.manifest["right"])
    period = int(fx.manifest["atr_period"])
    events = confirmed_pivots_with_centers(
        fx.htf_high, fx.htf_low, left, right, exclude_forming=True
    )
    compact = [(a, p, t) for a, p, t, _c in events]
    states = walk_swing_and_fibs(compact)
    n = len(fx.close)
    if _same_timeframe(fx):
        direction, f_a, f_b = expand_fib_states(n, states)
    else:
        direction, f_a, f_b = _expand_fib_on_chart(fx, states)
    atr = wilder_atr(fx.high, fx.low, fx.close, period)
    sig = zone_signal(fx.close, direction, f_a, f_b)
    return {
        "events": events,
        "states": states,
        "direction": direction,
        "fib_618": f_a,
        "fib_786": f_b,
        "atr14": atr,
        "signal": sig,
    }


def htf_available_at(confirm_open: datetime, htf_tf: str) -> datetime:
    """First instant the HTF confirmation bar is closed."""
    return confirm_open + timedelta(seconds=tf_seconds(htf_tf))


def chart_bar_close(bar_open: datetime, chart_tf: str) -> datetime:
    return bar_open + timedelta(seconds=tf_seconds(chart_tf))


def _expand_fib_on_chart(
    fx: Fixture,
    states: list[tuple[int, int, float, float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MTF: live when chart_bar_close >= htf_confirm_open + htf_period."""
    htf_times = [parse_bar_time(t) for t in fx.htf_times]
    chart_times = [parse_bar_time(t) for t in fx.times]
    htf_tf = str(fx.manifest["htf_tf"])
    chart_tf = str(fx.manifest["chart_tf"])
    timed: list[tuple[datetime, int, float, float]] = []
    for active_idx, direction, a, b in states:
        if active_idx < 0 or active_idx >= len(htf_times):
            raise ParityError(f"fib state active_idx {active_idx} outside HTF series")
        available = htf_available_at(htf_times[active_idx], htf_tf)
        timed.append((available, direction, a, b))
    n = len(chart_times)
    direction = np.zeros(n, dtype=int)
    f_a = np.full(n, np.nan)
    f_b = np.full(n, np.nan)
    state_i = 0
    cur_dir, cur_a, cur_b = 0, float("nan"), float("nan")
    for i, t in enumerate(chart_times):
        close_t = chart_bar_close(t, chart_tf)
        while state_i < len(timed) and timed[state_i][0] <= close_t:
            _ts, cur_dir, cur_a, cur_b = timed[state_i]
            state_i += 1
        direction[i] = cur_dir
        f_a[i] = cur_a
        f_b[i] = cur_b
    return direction, f_a, f_b


def compare_series(
    name: str,
    mql: np.ndarray,
    py: np.ndarray,
    times: list[str],
    abs_tol: float,
    start: int = 0,
) -> list[str]:
    if len(mql) != len(py):
        return [f"{name}: length mql={len(mql)} python={len(py)}"]
    errors: list[str] = []
    for i, (a, b) in enumerate(zip(mql, py, strict=True)):
        if i < start:
            continue
        if not _nan_close(float(a), float(b), abs_tol):
            errors.append(
                f"{name}[{i}] t={times[i]} mql={a} python={b} tol={abs_tol}"
            )
    return errors


def compare_pivots(fx: Fixture, events: list[tuple[int, float, int, int]]) -> list[str]:
    errors: list[str] = []
    right = int(fx.manifest["right"])
    py = [
        {
            "center_idx": c,
            "confirm_idx": a,
            "ptype": t,
            "price": p,
        }
        for a, p, t, c in events
    ]
    if len(py) != len(fx.pivots):
        errors.append(f"pivot count mql={len(fx.pivots)} python={len(py)}")
        return errors
    for i, (m, p) in enumerate(zip(fx.pivots, py, strict=True)):
        if m["center_idx"] != p["center_idx"] or m["confirm_idx"] != p["confirm_idx"]:
            errors.append(f"pivot[{i}] idx mql={m} python={p}")
        elif m["ptype"] != p["ptype"]:
            errors.append(f"pivot[{i}] ptype mql={m['ptype']} python={p['ptype']}")
        elif abs(m["price"] - p["price"]) > 1e-8:
            errors.append(
                f"pivot[{i}] price mql={m['price']} python={p['price']}"
            )
        elif m["confirm_idx"] != m["center_idx"] + right:
            errors.append(f"pivot[{i}] confirm != center+right")
        else:
            # confirm_time must be the HTF bar at confirm_idx
            if m["confirm_idx"] < len(fx.htf_times):
                expect = fx.htf_times[m["confirm_idx"]]
                if m["confirm_time"] != expect:
                    errors.append(
                        f"pivot[{i}] confirm_time mql={m['confirm_time']!r} "
                        f"expected {expect!r}"
                    )
    return errors


def verify_fixture(path: Path) -> dict[str, Any]:
    fx = load_fixture(path)
    assert_copy_complete(fx)
    assert_buffer_contract(fx)
    assert_timestamps_chrono(fx.times, "bars")
    assert_timestamps_chrono(fx.htf_times, "htf_bars")
    assert_closed_bar_signal(fx)
    assert_pivot_confirmation(fx)

    py = python_side(fx)
    abs_tol = float(fx.manifest.get("abs_tol", 1e-8))
    start = int(fx.manifest["compare_from_chart_idx"])
    if start < 0 or start > len(fx.times):
        raise ParityError(f"compare_from_chart_idx={start} out of range")
    errors: list[str] = []
    errors.extend(
        compare_series("atr14", fx.atr14, py["atr14"], fx.times, abs_tol, start)
    )
    errors.extend(
        compare_series("fib_618", fx.fib_618, py["fib_618"], fx.times, abs_tol, start)
    )
    errors.extend(
        compare_series("fib_786", fx.fib_786, py["fib_786"], fx.times, abs_tol, start)
    )
    errors.extend(
        compare_series(
            "swing_dir", fx.swing_dir, py["direction"], fx.times, abs_tol, start
        )
    )
    errors.extend(compare_pivots(fx, py["events"]))

    signal_kind = str(fx.manifest.get("signal_kind", "zone"))
    if signal_kind == "zone":
        errors.extend(
            compare_series("signal", fx.signal, py["signal"], fx.times, abs_tol, start)
        )
    elif signal_kind == "indicator_buffer":
        # Live export: do not claim full RSI/EMA confluence parity yet.
        # Still forbid activation before the triggering pivot is confirmed.
        errors.extend(_lookahead_on_buffers(fx, py["events"]))
    else:
        errors.append(f"unknown signal_kind={signal_kind!r}")

    if errors:
        preview = "\n  ".join(errors[:20])
        extra = f" (+{len(errors) - 20} more)" if len(errors) > 20 else ""
        raise ParityError(f"{len(errors)} mismatch(es):\n  {preview}{extra}")

    return {
        "ok": True,
        "path": str(fx.path),
        "n_bars": len(fx.times),
        "n_pivots": len(fx.pivots),
        "n_fib_states": len(py["states"]),
        "signal_kind": signal_kind,
        "signal_buffer": SIGNAL_BUFFER,
        "atr_method": "wilder",
    }


def _lookahead_on_buffers(
    fx: Fixture, events: list[tuple[int, float, int, int]]
) -> list[str]:
    """Fail if fib/swing/signal is live on a chart bar before any confirm time."""
    if not events:
        return []
    htf_times = [parse_bar_time(t) for t in fx.htf_times]
    chart_times = [parse_bar_time(t) for t in fx.times]
    htf_tf = str(fx.manifest["htf_tf"])
    chart_tf = str(fx.manifest["chart_tf"])
    first_avail: datetime | None = None
    for a, _p, _t, _c in events:
        if a < 0 or a >= len(htf_times):
            continue
        avail = htf_available_at(htf_times[a], htf_tf)
        if first_avail is None or avail < first_avail:
            first_avail = avail
    if first_avail is None:
        return []
    errors: list[str] = []
    for i, t in enumerate(chart_times):
        if chart_bar_close(t, chart_tf) >= first_avail:
            break
        if fx.swing_dir[i] != 0 and not np.isnan(fx.swing_dir[i]):
            errors.append(
                f"swing_dir lookahead at {fx.times[i]} before HTF available_at"
            )
        if not np.isnan(fx.fib_618[i]):
            errors.append(
                f"fib_618 lookahead at {fx.times[i]} before HTF available_at"
            )
        sig = fx.signal[i]
        if sig != 0 and not np.isnan(sig):
            errors.append(
                f"signal lookahead at {fx.times[i]} before HTF available_at"
            )
    return errors


# ---------------------------------------------------------------------------
# Synthetic fixture (committed, deterministic)
# ---------------------------------------------------------------------------
def build_synthetic_ohlc(
    n: int = 64,
    left: int = 5,
    right: int = 5,
    start: datetime | None = None,
) -> dict[str, Any]:
    """Planted pivot low + high so confirmation timing is known exactly."""
    if start is None:
        start = datetime(2024, 1, 2, 0, 0, 0)
    high = np.full(n, 100.40)
    low = np.full(n, 99.60)
    close = np.full(n, 100.00)
    open_ = np.full(n, 100.00)
    for i in range(n):
        wobble = 0.08 * ((i % 7) - 3)
        high[i] = 100.40 + abs(wobble)
        low[i] = 99.60 - abs(wobble)
        close[i] = 100.00 + wobble
        open_[i] = 100.00

    c_low, c_high = 20, 40
    low[c_low] = 90.00
    close[c_low] = 91.00
    open_[c_low] = 99.50
    high[c_high] = 120.00
    close[c_high] = 118.00
    open_[c_high] = 101.00
    for i in range(c_low - left, c_low + right + 1):
        if i != c_low and 0 <= i < n:
            low[i] = max(low[i], 91.20)
    for i in range(c_high - left, c_high + right + 1):
        if i != c_high and 0 <= i < n:
            high[i] = min(high[i], 118.80)

    # After the high confirms (c_high + right), park a few closes in the
    # golden zone so zone-signal is non-zero on closed bars only.
    confirm_high = c_high + right
    # bullish swing 90 → 120 → fib 61.8 = 101.46, 78.6 = 96.42
    for i in range(confirm_high, n - 1):
        close[i] = 99.00
        open_[i] = 99.20
        high[i] = 100.10
        low[i] = 97.80
    # forming bar stays outside the zone and must carry signal 0
    close[-1] = 104.00
    open_[-1] = 103.50
    high[-1] = 104.50
    low[-1] = 103.00

    times = [format_mql_time(start + timedelta(hours=i)) for i in range(n)]
    return {
        "times": times,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "c_low": c_low,
        "c_high": c_high,
        "left": left,
        "right": right,
    }


def _writer_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """FxAtrSeries clone used only to freeze fixture ATR columns.

    Intentionally not ``wilder_atr`` — a bug in the function under test must
    not rewrite the committed expected series.
    """
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    tr_sum = 0.0
    for i in range(1, period + 1):
        hl = float(high[i]) - float(low[i])
        hc = abs(float(high[i]) - float(close[i - 1]))
        lc = abs(float(low[i]) - float(close[i - 1]))
        tr_sum += max(hl, hc, lc)
    out[period] = tr_sum / period
    for i in range(period + 1, n):
        hl = float(high[i]) - float(low[i])
        hc = abs(float(high[i]) - float(close[i - 1]))
        lc = abs(float(low[i]) - float(close[i - 1]))
        tr = max(hl, hc, lc)
        out[i] = (out[i - 1] * (period - 1) + tr) / period
    return out


def write_synthetic_fixture(dest: Path) -> Path:
    """Write the frozen synthetic schema. Expected columns are hand-derived."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    raw = build_synthetic_ohlc()
    n = len(raw["times"])
    left, right = raw["left"], raw["right"]
    atr = _writer_atr(raw["high"], raw["low"], raw["close"], ATR_PERIOD)

    planted = (
        (PLANTED_LOW_CENTER, PLANTED_CONFIRM_LOW, -1, PLANTED_LOW_PRICE),
        (PLANTED_HIGH_CENTER, PLANTED_CONFIRM_HIGH, 1, PLANTED_HIGH_PRICE),
    )

    _write_bars(dest / "bars.csv", raw)
    _write_bars(dest / "htf_bars.csv", raw)
    with (dest / "buffers.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["idx", "time", "atr14", "fib_618", "fib_786", "swing_dir", "signal"]
        )
        for i in range(n):
            live = i >= FIB_LIVE_FROM
            fib_a = FIB_618 if live else float("nan")
            fib_b = FIB_786 if live else float("nan")
            swing = 1 if live else 0
            in_zone = live and (min(FIB_618, FIB_786) <= raw["close"][i] <= max(
                FIB_618, FIB_786
            ))
            sig = swing if (in_zone and i < n - 1) else 0
            w.writerow(
                [
                    i,
                    raw["times"][i],
                    _csv_num(atr[i]),
                    _csv_num(fib_a),
                    _csv_num(fib_b),
                    swing,
                    sig,
                ]
            )
    with (dest / "pivots.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "center_idx",
                "confirm_idx",
                "center_time",
                "confirm_time",
                "ptype",
                "price",
            ]
        )
        for center, confirm, ptype, price in planted:
            w.writerow(
                [
                    center,
                    confirm,
                    raw["times"][center],
                    raw["times"][confirm],
                    ptype,
                    f"{price:.8f}",
                ]
            )

    copy = {
        "rates": {"requested": n, "copied": n},
        "htf_rates": {"requested": n, "copied": n},
        "buffers": {str(i): {"requested": n, "copied": n} for i in range(11)},
    }
    manifest = {
        "schema": SCHEMA,
        "source": "synthetic",
        "symbol": "PARITY",
        "chart_tf": "H1",
        "htf_tf": "H1",
        "left": left,
        "right": right,
        "atr_period": ATR_PERIOD,
        "atr_method": "wilder",
        "signal_buffer": SIGNAL_BUFFER,
        "signal_shift": SIGNAL_SHIFT,
        "closed_bar_only": True,
        "signal_kind": "zone",
        "export_ok": True,
        "htf_scan_bars": n,
        "compare_from_chart_idx": 0,
        "indicator": "ForexHtfPivotsFib",
        "buffer_map": {str(k): v for k, v in HTF_FIB_BUFFERS.items()},
        "copy": copy,
        "n_bars": n,
        "n_htf_bars": n,
        "n_pivots": len(planted),
        "abs_tol": 1e-8,
        "notes": (
            "Frozen synthetic H1=HTF series. Expected fib/ATR/signal columns "
            "are hand-derived (PLANTED_*/FIB_*), not htf_fib_core output. "
            "No indicator_version: this fixture never ran ForexHtfPivotsFib. "
            "Live dump: ExportHtfFibParityFixture (signal_kind=indicator_buffer)."
        ),
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return dest


def _csv_num(value: float) -> str:
    if value != value:  # NaN
        return ""
    return f"{float(value):.8f}"


def _write_bars(path: Path, raw: dict[str, Any]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["idx", "time", "open", "high", "low", "close", "tick_volume"])
        n = len(raw["times"])
        for i in range(n):
            w.writerow(
                [
                    i,
                    raw["times"][i],
                    f"{raw['open'][i]:.8f}",
                    f"{raw['high'][i]:.8f}",
                    f"{raw['low'][i]:.8f}",
                    f"{raw['close'][i]:.8f}",
                    100,
                ]
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "fixture",
        nargs="?",
        default=str(DEFAULT_FIXTURE),
        help="fixture directory (default: committed synthetic)",
    )
    parser.add_argument(
        "--write-synthetic",
        metavar="DIR",
        help="write a fresh synthetic fixture to DIR and exit",
    )
    args = parser.parse_args(argv)
    if args.write_synthetic:
        dest = write_synthetic_fixture(Path(args.write_synthetic))
        print(f"wrote synthetic fixture → {dest}")
        return 0
    try:
        report = verify_fixture(Path(args.fixture))
    except ParityError as exc:
        print(f"PARITY FAIL: {exc}", file=sys.stderr)
        return 1
    print("MQL5 ↔ Python parity PASSED")
    for key, value in report.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
