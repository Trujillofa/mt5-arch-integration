#!/usr/bin/env python3
"""Signal-edge diagnostic — does a family carry information worth its friction?

Offline research only. Read-only: writes nothing, ranks nothing, selects nothing.
promote / live_go are not concepts here — this tool cannot produce a config.

WHY THIS EXISTS
---------------
An exit-grid screen answers "did any config make money". It cannot separate the
two reasons a screen fails:

  (a) the entry carries no directional information at all, or
  (b) the entry carries information, but less of it than the round trip costs.

Those need opposite responses. (a) means abandon the family. (b) means the
family is real and the execution model / timeframe / cost book is what has to
change. The EURUSD NY-scalp v1 screen conflated them: pooled gross PF was ~1.00,
which reads as (a), but per-family the pool was hiding a genuinely predictive
mean-reversion family, a reliably ANTI-predictive trend family, and noise.

WHAT IT MEASURES
----------------
For every signal bar, the signed forward return from the bar the simulator
would actually fill on (the open of i+1), at several horizons, in points:

    r_h = (close[i + 1 + h] - open[i + 1]) * side / point

Reported against the round-trip friction of the lock's cost book. The decision
rule is a comparison, not a search:

    max_h mean(r_h)  <  friction_points   =>  family is dead before exits.

No exit, no stop, no sizing, no compounding enters this number, so it cannot be
tuned. Run it BEFORE building an exit grid, not after.

CAUSALITY
---------
Inherited from whatever produces `signals`: this module never builds a signal.
It only shifts by +1 bar to the fill and looks forward from there. A family
whose signals are causal stays causal here.

WINDOWS
-------
`mask` restricts to develop. Holdout is not special-cased and not excluded on
your behalf — pass the develop mask. Reporting a diagnostic on holdout data is
still a peek; this tool will not stop you, the caller's discipline must.

Usage:
    python3 scripts/signal_edge_diagnostic.py                  # EURUSD lane
    python3 scripts/signal_edge_diagnostic.py --lane eurusd
    python3 scripts/signal_edge_diagnostic.py --lane xau
    python3 scripts/signal_edge_diagnostic.py --lane us_index
    python3 scripts/signal_edge_diagnostic.py --lane all --by-year
    python3 scripts/signal_edge_diagnostic.py --horizons 5,20,50 --by-year
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

DEFAULT_HORIZONS = (5, 10, 20, 50, 100)

# Lane friction / point books (lock cost books; not searched here).
EURUSD_FRICTION_PTS = 22.0
EURUSD_POINT = 1e-5
EURUSD_HOLDOUT = "2025-03-01"

XAU_FRICTION_PTS = 18.0
XAU_POINT = 0.01
XAU_HOLDOUT = "2026-01-01"

US_FRICTION_PTS = 80.0
US_POINT = 0.01
US_HOLDOUT_V1 = "2026-06-01"
US_HOLDOUT_V4 = "2026-07-01"


@dataclass(frozen=True)
class HorizonStat:
    horizon: int
    n: int
    mean_pts: float
    median_pts: float
    t_stat: float


@dataclass
class EdgeResult:
    name: str
    n_signals: int
    friction_pts: float
    stats: list[HorizonStat] = field(default_factory=list)

    @property
    def best(self) -> HorizonStat | None:
        return max(self.stats, key=lambda s: s.mean_pts) if self.stats else None

    @property
    def worst(self) -> HorizonStat | None:
        return min(self.stats, key=lambda s: s.mean_pts) if self.stats else None

    @property
    def verdict(self) -> str:
        """CLEARS-FRICTION / ANTI / COST-BOUND / DEAD. Never a recommendation.

        Order matters. A family can be significantly negative at one horizon and
        trivially positive at another (trend_continuation is +0.06 pts at H5 and
        -11.85 at H50); calling that COST-BOUND because the max is above zero
        would invert its meaning, so ANTI is tested before the positive cases.
        """
        b, w = self.best, self.worst
        if b is None or w is None or self.n_signals == 0:
            return "EMPTY"
        if b.mean_pts >= self.friction_pts and b.t_stat >= 2.0:
            return "CLEARS-FRICTION"
        if w.mean_pts < 0 and w.t_stat <= -2.0:
            return "ANTI"
        if b.mean_pts > 0 and b.t_stat >= 2.0:
            return "COST-BOUND"
        return "DEAD"

    @property
    def bias_warnings(self) -> tuple[str, ...]:
        """Thin-n positive labels (does not change ``verdict``)."""
        from research_bias_gates import detect_edge_verdict_warnings

        return detect_edge_verdict_warnings(
            verdict=self.verdict, n_signals=self.n_signals
        )


@dataclass(frozen=True)
class LaneFamily:
    """One importable ±1 signal series on a develop mask (adapters only)."""

    name: str
    open: np.ndarray
    close: np.ndarray
    signals: np.ndarray
    develop: np.ndarray
    years: np.ndarray
    point: float
    friction_pts: float
    holdout_iso: str


def forward_edge(
    open_: np.ndarray,
    close: np.ndarray,
    signals: np.ndarray,
    mask: np.ndarray,
    *,
    point: float,
    friction_pts: float,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    name: str = "family",
) -> EdgeResult:
    """Signed forward return from the fill bar, in points, per horizon.

    `signals` is -1 / 0 / +1 on the DECISION bar i. The fill is open[i+1], which
    is what the simulator uses, so the diagnostic and the backtest share an entry.
    """
    n = len(close)
    if not (len(open_) == len(signals) == len(mask) == n):
        raise ValueError("open_/close/signals/mask must be the same length")
    if point <= 0:
        raise ValueError("point must be positive")

    idx = np.flatnonzero((np.asarray(signals) != 0) & np.asarray(mask))
    idx = idx[idx + 1 < n]
    res = EdgeResult(name=name, n_signals=int(idx.size), friction_pts=float(friction_pts))
    if idx.size == 0:
        return res

    fill = np.asarray(open_, dtype=float)[idx + 1]
    side = np.asarray(signals, dtype=float)[idx]
    for h in horizons:
        j = np.minimum(idx + 1 + h, n - 1)
        r = (np.asarray(close, dtype=float)[j] - fill) * side / point
        sd = float(r.std(ddof=1)) if r.size > 1 else 0.0
        t = float(r.mean() / (sd / np.sqrt(r.size))) if sd > 0 else 0.0
        res.stats.append(
            HorizonStat(
                horizon=int(h),
                n=int(r.size),
                mean_pts=float(r.mean()),
                median_pts=float(np.median(r)),
                t_stat=t,
            )
        )
    return res


def format_table(results: list[EdgeResult], horizons: tuple[int, ...]) -> str:
    """One row per family. Friction is printed once — it is the decision line."""
    if not results:
        return "(no families)\n"
    fr = results[0].friction_pts
    head = f"{'family':>28} {'n':>7} " + "".join(f"{'H' + str(h):>9}" for h in horizons)
    head += f"{'best':>7}{'t':>7}{'worst':>8}{'t':>7}  verdict"
    out = [
        "Signed forward return from the fill bar, in POINTS.",
        f"Round-trip friction = {fr:.1f} pts — a family must beat this to be tradeable.",
        "",
        head,
        "-" * len(head),
    ]
    for r in results:
        if not r.stats:
            out.append(
                f"{r.name:>28} {0:>7} " + " " * (9 * len(horizons)) + f"{'':>9}  EMPTY"
            )
            continue
        by_h = {s.horizon: s for s in r.stats}
        row = f"{r.name:>28} {r.n_signals:>7,} "
        row += "".join(
            f"{by_h[h].mean_pts:>9.2f}" if h in by_h else f"{'':>9}" for h in horizons
        )
        b, w = r.best, r.worst
        row += (
            f"{b.mean_pts:>7.1f}{b.t_stat:>7.2f}"
            f"{w.mean_pts:>8.1f}{w.t_stat:>7.2f}  {r.verdict}"
        )
        out.append(row)
        for wmsg in r.bias_warnings:
            out.append(f"  ! bias: {wmsg}")
    return "\n".join(out) + "\n"


# --- EURUSD NY-scalp lane wiring ---------------------------------------------


def _eurusd_families(csv_path: Path, holdout_iso: str, one_per_day: bool):
    """Import the frozen lane and return (data, {name: signals}, develop mask)."""
    import pandas as pd
    from eurusd_ny_scalp_core import build_context, load_eurusd_m5

    d = load_eurusd_m5(csv_path)
    ho = date.fromisoformat(holdout_iso)
    et = pd.to_datetime(pd.Series(d.et_key).astype(str))
    develop = (et.dt.date < ho).to_numpy()
    years = et.dt.year.to_numpy()
    ctx = build_context(d, one_per_day=one_per_day)
    return d, {k: v.signals for k, v in ctx.items()}, develop, years


def _eurusd_lane(
    csv_path: Path, holdout_iso: str, one_per_day: bool, friction_pts: float, point: float
) -> list[LaneFamily]:
    d, fams, develop, years = _eurusd_families(csv_path, holdout_iso, one_per_day)
    return [
        LaneFamily(
            name=name,
            open=d.open,
            close=d.close,
            signals=sig,
            develop=develop,
            years=years,
            point=point,
            friction_pts=friction_pts,
            holdout_iso=holdout_iso,
        )
        for name, sig in fams.items()
    ]


# --- XAU multi-instrument lane (one runnable producer) -----------------------


def _xau_lane(root: Path) -> list[LaneFamily]:
    """Import build_signal_sides; load package CSVs; develop = server_time < holdout."""
    import pandas as pd
    import xau_family_exog_london_fx_cosign_xau_follow_flat as fam

    pkg = root / "results" / "instrument_data_packages" / "CURRENT" / "instrument_data"
    paths = {
        "XAUUSD": pkg / "xauusd_h1.csv",
        "EURUSD": pkg / "eurusd_h1.csv",
        "GBPUSD": pkg / "gbpusd_h1.csv",
    }
    for sym, p in paths.items():
        if not p.is_file():
            raise FileNotFoundError(f"XAU package CSV missing: {p} ({sym})")

    raw = {sym: pd.read_csv(p) for sym, p in paths.items()}
    aligned = fam.align_intersection(raw)
    ch = fam.load_charter()
    params = fam._params_from_charter(ch)
    sides = fam.build_signal_sides(
        aligned, coincident_hours=list(params["coincident_hours"])
    )
    xau = aligned["XAUUSD"]
    times = pd.to_datetime(xau["time"])
    ho = pd.Timestamp(XAU_HOLDOUT)
    develop = (times < ho).to_numpy()
    years = times.dt.year.to_numpy()
    point = float(params["point_size"])
    return [
        LaneFamily(
            name=fam.FAMILY_ID,
            open=xau["open"].to_numpy(float),
            close=xau["close"].to_numpy(float),
            signals=np.asarray(sides, dtype=np.int8),
            develop=develop,
            years=years,
            point=point,
            friction_pts=XAU_FRICTION_PTS,
            holdout_iso=XAU_HOLDOUT,
        )
    ]


# --- US index session lane ---------------------------------------------------


def _us_develop(times: list[datetime], holdout_iso: str) -> tuple[np.ndarray, np.ndarray]:
    from us_index_session_core import to_et

    ho = date.fromisoformat(holdout_iso)
    et = [to_et(t) for t in times]
    develop = np.array([e.date() < ho for e in et], dtype=bool)
    years = np.array([e.year for e in et], dtype=np.int32)
    return develop, years


def _us_index_lane(root: Path) -> tuple[list[LaneFamily], list[dict[str, str]]]:
    """Import frozen US-index signal producers; prototype params = first grid cell."""
    from us_index_session_autoresearch import (  # noqa: WPS433
        _et_arrays,
        _or_and_vwap,
        signal_series,
    )
    from us_index_session_autoresearch_v2 import bounce_signals, macd_signals
    from us_index_session_autoresearch_v3 import (
        div_signals,
        fvg_signals,
        sweep_signals,
    )
    from us_index_session_autoresearch_v4 import (
        cvd_signals,
        orb_regime_signals,
        poc_signals,
    )
    from us_index_session_autoresearch_v5 import (
        combine_lock,
        gap_fade_signals,
        htf_lock_orb_signals,
        us30_cosign_signals,
    )
    from us_index_session_autoresearch_v6 import (
        DEFAULT_XAU_H1 as V6_XAU_H1,
    )
    from us_index_session_autoresearch_v6 import (
        REGIME_MOM,
        REGIME_MR,
        london_gated_or_signals,
        mom_or_signals,
        mr_gap_signals,
    )
    from us_index_session_autoresearch_v6 import (
        load_h1_hc as load_v6_xau_h1,
    )
    from us_index_session_autoresearch_v7 import zscore_vol_signals
    from us_index_session_backtest import load_m5_csv, parse_meta
    from us_index_session_core import (
        atr_expanding,
        cash_adr_series,
        cash_open_gap_pct,
        completed_daily_donch_state,
        completed_daily_regime_state,
        completed_h4_ema_bias,
        ema_series,
        ib_false_break_signals,
        london_et_displacement,
        london_feature_on_m5,
        macd_series,
        pre_ny_liquidity_levels,
        prior_cash_close_series,
        prior_day_poc,
        proxy_cvd_series,
        rolling_zscore_typical,
        rsi_series,
        scalp_signal_series,
        to_utc,
        wilder_atr,
    )
    from us_index_session_htf import (
        completed_daily_sma50_slope,
        fib_pullback_signals,
        h4_impulses,
        squeeze_breakout_signals,
    )

    skipped: list[dict[str, str]] = []
    out: list[LaneFamily] = []

    csv100 = root / "results" / "us_index_data" / "history_US100_M5.csv"
    meta100 = root / "results" / "us_index_data" / "symbol_meta_US100.csv"
    csv30 = root / "results" / "us_index_data" / "history_US30_M5.csv"
    meta30 = root / "results" / "us_index_data" / "symbol_meta_US30.csv"
    h1_csv = root / "results" / "us_index_data" / "history_US100_H1.csv"
    h4_csv = root / "results" / "us_index_data" / "history_US100_H4.csv"
    daily_csv = root / "results" / "us_index_data" / "history_US100_Daily.csv"

    if not csv100.is_file():
        raise FileNotFoundError(f"US100 M5 missing: {csv100}")

    meta = parse_meta(meta100) if meta100.is_file() else {}
    offset = int(float(meta.get("server_utc_offset_sec") or 10800))
    df = load_m5_csv(csv100, offset)
    times = [to_utc(ts.to_pydatetime()) for ts in df["time_utc"]]
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    open_ = df["open"].to_numpy(float)
    vol = df["tick_volume"].to_numpy(float)
    mins, keys, dow, ny = _et_arrays(times)
    atr14 = wilder_atr(high, low, close, 14)
    or_h, or_l, ready, vwap = _or_and_vwap(mins, keys, ny, high, low, close, vol, 15)
    ema_f = ema_series(close, 8)
    ema_s = ema_series(close, 21)
    rsi7 = rsi_series(close, 7)
    _macd_line, _macd_sig, macd_hist = macd_series(close, 12, 26, 9)
    expanding = atr_expanding(
        wilder_atr(high, low, close, 7), wilder_atr(high, low, close, 28), 1.0
    )
    asia_h, asia_l, lon_h, lon_l, pdh, pdl = pre_ny_liquidity_levels(
        times, high, low, keys
    )
    cvd = proxy_cvd_series(keys, open_, close, vol)
    poc = prior_day_poc(keys, high, low, vol, bin_price=2.0, kind="volume")
    prior_c = prior_cash_close_series(mins, keys, close)
    gap = cash_open_gap_pct(mins, keys, open_, prior_c)
    adr14 = cash_adr_series(mins, keys, high, low, 14)
    h4_bias = completed_h4_ema_bias(times, close)
    donch = completed_daily_donch_state(keys, high, low, close, n=20)
    lock_h4 = combine_lock("h4", h4_bias, donch)
    z12, _zmu, _zsig, vol_mu = rolling_zscore_typical(
        high, low, close, vol, 12, include_i=False
    )

    def _add(
        name: str,
        sigs: np.ndarray,
        holdout_iso: str,
        *,
        open_arr: np.ndarray | None = None,
        close_arr: np.ndarray | None = None,
        times_arr: list[datetime] | None = None,
    ) -> None:
        t_use = times_arr if times_arr is not None else times
        develop, years = _us_develop(t_use, holdout_iso)
        out.append(
            LaneFamily(
                name=name,
                open=open_ if open_arr is None else open_arr,
                close=close if close_arr is None else close_arr,
                signals=np.asarray(sigs, dtype=np.int8),
                develop=develop,
                years=years,
                point=US_POINT,
                friction_pts=US_FRICTION_PTS,
                holdout_iso=holdout_iso,
            )
        )

    # --- develop lock / scalp (holdout 2026-06-01) ---
    _add(
        "ny_cash_orb_vwap_ema_flat",
        scalp_signal_series(times, high, low, close, vol),
        US_HOLDOUT_V1,
    )
    _add(
        "us_index_session_develop_v1",
        signal_series(
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            vwap,
            ema_f,
            ema_s,
            atr14,
            or_minutes=15,
            entry_end_min=10 * 60 + 30,
            use_vwap=True,
            use_ema=True,
            one_per_day=True,
        ),
        US_HOLDOUT_V1,
    )
    _add(
        "ny_cash_vwap_bounce_rsi",
        bounce_signals(
            close,
            mins,
            keys,
            dow,
            ny,
            vwap,
            atr14,
            rsi7,
            entry_end_min=10 * 60,
            atr_dev=1.0,
            rsi_ob=70.0,
            rsi_os=30.0,
            one_per_day=True,
        ),
        US_HOLDOUT_V1,
    )
    _add(
        "ny_cash_ema_macd",
        macd_signals(
            mins,
            keys,
            dow,
            ny,
            ema_series(close, 5),
            ema_series(close, 20),
            macd_hist,
            entry_end_min=10 * 60 + 30,
            one_per_day=True,
            cross_only=True,
        ),
        US_HOLDOUT_V1,
    )
    sweep_sigs, _tgt = sweep_signals(
        open_,
        high,
        low,
        close,
        mins,
        keys,
        dow,
        asia_h,
        asia_l,
        lon_h,
        lon_l,
        pdh,
        pdl,
        or_h,
        or_l,
        ready,
        use_asia=False,
        use_london=False,
        use_pdh=True,
        use_or=True,
        wick_frac=0.4,
        entry_end_min=10 * 60 + 30,
        one_per_day=True,
        exit_tag="flatten",
    )
    _add("ny_cash_liquidity_sweep", sweep_sigs, US_HOLDOUT_V1)
    fvg_sigs, _ft = fvg_signals(
        high,
        low,
        close,
        mins,
        keys,
        dow,
        atr14,
        min_gap_atr=0.15,
        entry_end_min=11 * 60 + 30,
        one_per_day=True,
    )
    _add("ny_cash_fvg_mitigation", fvg_sigs, US_HOLDOUT_V1)

    if csv30.is_file():
        meta30d = parse_meta(meta30) if meta30.is_file() else {}
        off30 = int(float(meta30d.get("server_utc_offset_sec") or 10800))
        df30 = load_m5_csv(csv30, off30)
        pair = (
            df[["time_utc", "open", "high", "low", "close"]]
            .merge(
                df30[["time_utc", "open", "high", "low", "close"]],
                on="time_utc",
                suffixes=("_a", "_b"),
            )
            .sort_values("time_utc")
            .reset_index(drop=True)
        )
        p_times = [to_utc(ts.to_pydatetime()) for ts in pair["time_utc"]]
        p_mins, p_keys, p_dow, _pny = _et_arrays(p_times)
        p_open = pair["open_a"].to_numpy(float)
        p_close = pair["close_a"].to_numpy(float)
        _add(
            "us100_us30_divergence",
            div_signals(
                pair["high_a"].to_numpy(float),
                pair["low_a"].to_numpy(float),
                pair["high_b"].to_numpy(float),
                pair["low_b"].to_numpy(float),
                p_mins,
                p_keys,
                p_dow,
                lookback=6,
                entry_end_min=11 * 60 + 30,
                one_per_day=True,
            ),
            US_HOLDOUT_V1,
            open_arr=p_open,
            close_arr=p_close,
            times_arr=p_times,
        )
        u30_open = pair["open_b"].to_numpy(float)
        u30_close = pair["close_b"].to_numpy(float)
        u30_atr = wilder_atr(
            pair["high_b"].to_numpy(float),
            pair["low_b"].to_numpy(float),
            u30_close,
            14,
        )
        _add(
            "exog_us30_ny_cash_cosign_us100_follow",
            us30_cosign_signals(
                u30_open,
                u30_close,
                u30_atr,
                p_mins,
                p_keys,
                p_dow,
                min_atr_k=0.0,
                one_per_day=True,
            ),
            US_HOLDOUT_V4,
            open_arr=p_open,
            close_arr=p_close,
            times_arr=p_times,
        )
    else:
        skipped.append(
            {
                "family_id": "us100_us30_divergence",
                "reason": "US30 M5 CSV missing; cannot align for div_signals",
            }
        )
        skipped.append(
            {
                "family_id": "exog_us30_ny_cash_cosign_us100_follow",
                "reason": "US30 M5 CSV missing; cannot align for us30_cosign_signals",
            }
        )

    # --- v4+ (holdout 2026-07-01) ---
    _add(
        "vol_regime_orb",
        orb_regime_signals(
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            expanding,
            entry_end_min=10 * 60 + 30,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )
    _add(
        "tick_proxy_cvd",
        cvd_signals(
            high,
            low,
            cvd,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            pdh,
            pdl,
            expanding,
            level="or",
            lookback=6,
            regime_gate=True,
            entry_end_min=10 * 60 + 30,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )
    poc_sigs, _pt = poc_signals(
        close,
        vol,
        atr14,
        poc,
        mins,
        keys,
        dow,
        expanding,
        atr_dev=1.0,
        regime_gate=True,
        entry_end_min=10 * 60 + 30,
        one_per_day=True,
    )
    _add("prior_poc_reversion", poc_sigs, US_HOLDOUT_V4)
    _add(
        "ny_cash_gap_fade_adr",
        gap_fade_signals(
            close,
            mins,
            keys,
            dow,
            gap,
            adr14,
            prior_c,
            gap_min=0.005,
            gap_max=0.01,
            adr_k=0.4,
            entry="next_0930",
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )
    _add(
        "htf_lock_orb",
        htf_lock_orb_signals(
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            lock_h4,
            entry_end_min=11 * 60 + 30,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )

    regime_st, _hu, _ad = completed_daily_regime_state(
        keys, open_, high, low, close, atr_n=20, hurst_lb=32
    )
    _add(
        "daily_regime_switch:mom_or",
        mom_or_signals(
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            regime_st == REGIME_MOM,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )
    _add(
        "daily_regime_switch:mr_gap",
        mr_gap_signals(
            mins,
            keys,
            dow,
            gap,
            prior_c,
            regime_st == REGIME_MR,
            gap_min=0.005,
            gap_max=0.02,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )

    xau_h1 = Path(V6_XAU_H1)
    if xau_h1.is_file():
        xau = load_v6_xau_h1(xau_h1, offset)
        x_times = [to_utc(ts.to_pydatetime()) for ts in xau["time_utc"]]
        feat = london_et_displacement(
            x_times,
            xau["open"].to_numpy(float),
            xau["high"].to_numpy(float),
            xau["low"].to_numpy(float),
            xau["close"].to_numpy(float),
        )
        x_sign = london_feature_on_m5(keys, mins, feat, "sign")
        x_disp = london_feature_on_m5(keys, mins, feat, "disp")
        x_atr = london_feature_on_m5(keys, mins, feat, "atr")
        _add(
            "london_xau_fx_risk_gate",
            london_gated_or_signals(
                close,
                mins,
                keys,
                dow,
                or_h,
                or_l,
                ready,
                x_sign,
                x_disp,
                x_atr,
                min_disp_atr=0.5,
                one_per_day=True,
            ),
            US_HOLDOUT_V4,
        )
    else:
        skipped.append(
            {
                "family_id": "london_xau_fx_risk_gate",
                "reason": f"FP XAUUSD.r H1.hc missing: {xau_h1}",
            }
        )

    _add(
        "ib_false_breakout_fade",
        ib_false_break_signals(
            high,
            low,
            close,
            mins,
            keys,
            dow,
            or_h,
            or_l,
            ready,
            entry_end_min=11 * 60 + 30,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )
    _add(
        "m5_zscore_tick_vol_exhaustion",
        zscore_vol_signals(
            z12,
            vol,
            vol_mu,
            mins,
            keys,
            dow,
            z_thr=2.0,
            vol_k=1.5,
            entry_start_min=9 * 60 + 45,
            entry_end_min=15 * 60,
            one_per_day=True,
        ),
        US_HOLDOUT_V4,
    )

    # HTF lane (H1 / H4 / Daily)
    if h1_csv.is_file() and h4_csv.is_file() and daily_csv.is_file():
        h1 = load_m5_csv(h1_csv, offset)
        h4 = load_m5_csv(h4_csv, offset)
        daily = load_m5_csv(daily_csv, offset)
        h1_times = [to_utc(ts.to_pydatetime()) for ts in h1["time_utc"]]
        h1_high = h1["high"].to_numpy(float)
        h1_low = h1["low"].to_numpy(float)
        h1_close = h1["close"].to_numpy(float)
        h1_open = h1["open"].to_numpy(float)
        h1_mins, h1_keys, h1_dow, _h1ny = _et_arrays(h1_times)
        h4_times = [to_utc(ts.to_pydatetime()) for ts in h4["time_utc"]]
        h4_high = h4["high"].to_numpy(float)
        h4_low = h4["low"].to_numpy(float)
        h4_close = h4["close"].to_numpy(float)
        h4_atr = wilder_atr(h4_high, h4_low, h4_close, 14)
        d_times = [to_utc(ts.to_pydatetime()) for ts in daily["time_utc"]]
        slope = completed_daily_sma50_slope(
            h1_times, d_times, daily["close"].to_numpy(float)
        )
        _add(
            "h1_volatility_squeeze_breakout",
            squeeze_breakout_signals(
                h1_close,
                h1_high,
                h1_low,
                h1_mins,
                h1_keys,
                h1_dow,
                slope,
                bb_k=2.0,
                kc_atr_mult=1.5,
                one_per_day=True,
            ),
            US_HOLDOUT_V4,
            open_arr=h1_open,
            close_arr=h1_close,
            times_arr=h1_times,
        )
        imps = h4_impulses(
            h4_high,
            h4_low,
            h4_close,
            h4_times,
            h4_atr,
            left=3,
            right=2,
            k=2.0,
        )
        fib_sigs, _sl, _tp = fib_pullback_signals(
            h1_close,
            h1_high,
            h1_low,
            h1_times,
            h1_mins,
            h1_dow,
            imps,
            entry="close_in_zone",
        )
        _add(
            "h4_impulse_fib_pullback",
            fib_sigs,
            US_HOLDOUT_V4,
            open_arr=h1_open,
            close_arr=h1_close,
            times_arr=h1_times,
        )
    else:
        skipped.append(
            {
                "family_id": "h1_volatility_squeeze_breakout",
                "reason": "US100 H1/H4/Daily CSV missing for HTF adapter",
            }
        )
        skipped.append(
            {
                "family_id": "h4_impulse_fib_pullback",
                "reason": "US100 H1/H4/Daily CSV missing for HTF adapter",
            }
        )

    return out, skipped


# Inventory non-runnable / closed rows (Phase Inventory). Not re-wired here.
INVENTORY_SKIPPED: list[dict[str, str]] = [
    {
        "family_id": "bb_rsi",
        "reason": "KILL_BB_RSI_LINE; entry embedded in backtest.simulate(mode='bb_rsi'); "
        "no exportable ±1 signal_fn",
    },
    {
        "family_id": "donchian_turtle",
        "reason": "KILL_DONCHIAN_LINE; logic in simulate_donchian(); no exportable ±1 signal_fn",
    },
    {
        "family_id": "prior_day_high_break",
        "reason": "KILL_PRIOR_DAY_HIGH_BREAK; entry embedded in simulate(); "
        "no exportable ±1 signal_fn",
    },
    {
        "family_id": "tod_london_ny_flat",
        "reason": "PROTOCOL_NULL_INVALID / SCREEN_FAIL; entry embedded in simulate(); "
        "no exportable ±1 signal_fn",
    },
    {
        "family_id": "server_hour_window_flat",
        "reason": "SCREEN_FAIL ZERO_PRIMARY_PASSERS; entry embedded in simulate(); "
        "no exportable ±1 signal_fn",
    },
    {
        "family_id": "early_server_range_break_flat",
        "reason": "SCREEN_FAIL; entry embedded in simulate(); no exportable ±1 signal_fn",
    },
    {
        "family_id": "day_open_reclaim_flat",
        "reason": "SCREEN_FAIL; entry embedded in simulate(); no exportable ±1 signal_fn",
    },
    {
        "family_id": "joint_london_open_cosign_fade_flat",
        "reason": "SCREEN_FAIL; cosign fade inside simulate_joint(); no exportable ±1 signal_fn",
    },
    {
        "family_id": "asia_box_london_sweep_fade_flat",
        "reason": "SCREEN_FAIL; entry embedded in simulate(); no exportable ±1 signal_fn",
    },
    {
        "family_id": "macro_news_event_api",
        "reason": "skipped in lock (no usable news CSV / DISCARD surprise-drift); never implemented",
    },
    {
        "family_id": "us_index_session_v4_cost_size_once",
        "reason": "diagnostic_replay of already-closed winners; not a new signal family",
    },
]


def _print_lane(families: list[LaneFamily], horizons: tuple[int, ...], by_year: bool) -> None:
    if not families:
        print("(no families wired for this lane)\n")
        return
    # Group by (holdout, friction) so the develop header matches each mask.
    by_key: dict[tuple[str, float], list[LaneFamily]] = {}
    for f in families:
        by_key.setdefault((f.holdout_iso, f.friction_pts), []).append(f)
    for (ho, fr), group in by_key.items():
        n_dev = int(group[0].develop.sum())
        n_all = len(group[0].develop)
        print(f"develop = date < {ho}   bars {n_dev:,} / {n_all:,}   friction={fr:.1f}")
        print()
        results = [
            forward_edge(
                f.open,
                f.close,
                f.signals,
                f.develop,
                point=f.point,
                friction_pts=f.friction_pts,
                horizons=horizons,
                name=f.name,
            )
            for f in group
        ]
        print(format_table(results, horizons))

        if by_year:
            h = 50 if 50 in horizons else horizons[-1]
            print(f"Per-year stability at H{h} (develop only):")
            print(f"{'family':>28} {'year':>6} {'n':>7} {'mean':>9} {'median':>9} {'t':>7}")
            for f in group:
                for y in sorted(set(f.years[f.develop])):
                    sub = f.develop & (f.years == y)
                    r = forward_edge(
                        f.open,
                        f.close,
                        f.signals,
                        sub,
                        point=f.point,
                        friction_pts=f.friction_pts,
                        horizons=(h,),
                        name=f.name,
                    )
                    if r.n_signals < 50:
                        continue
                    s = r.stats[0]
                    print(
                        f"{f.name:>28} {y:>6} {s.n:>7,} {s.mean_pts:>9.2f} "
                        f"{s.median_pts:>9.2f} {s.t_stat:>7.2f}"
                    )
                print()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--lane",
        default="eurusd",
        choices=("eurusd", "xau", "us_index", "all"),
        help="which frozen lane adapter to run (default: eurusd)",
    )
    ap.add_argument("--csv", default="results/eurusd_data/history_EURUSD.csv")
    ap.add_argument(
        "--holdout",
        default=EURUSD_HOLDOUT,
        help="ET date for EURUSD develop mask; develop is strictly before",
    )
    ap.add_argument("--horizons", default="5,10,20,50,100")
    ap.add_argument("--point", type=float, default=EURUSD_POINT)
    ap.add_argument(
        "--friction-pts",
        type=float,
        default=EURUSD_FRICTION_PTS,
        help="EURUSD round trip: median spread + 2 x slippage (lock cost book)",
    )
    ap.add_argument("--one-per-day", action="store_true")
    ap.add_argument("--by-year", action="store_true", help="also break the best horizon out by year")
    args = ap.parse_args()

    horizons = tuple(int(x) for x in args.horizons.split(","))
    root = _ROOT
    csv = Path(args.csv)
    if not csv.is_absolute():
        csv = root / csv

    lanes = ("eurusd", "xau", "us_index") if args.lane == "all" else (args.lane,)
    for lane in lanes:
        print(f"=== lane={lane} ===")
        if lane == "eurusd":
            families = _eurusd_lane(
                csv, args.holdout, args.one_per_day, args.friction_pts, args.point
            )
            _print_lane(families, horizons, args.by_year)
        elif lane == "xau":
            families = _xau_lane(root)
            _print_lane(families, horizons, args.by_year)
        else:
            families, _runtime_skips = _us_index_lane(root)
            _print_lane(families, horizons, args.by_year)
        print()

    print("Reading: CLEARS-FRICTION = worth an exit grid. COST-BOUND = real signal,")
    print("too small to pay for itself — change execution/timeframe, not exits.")
    print("DEAD = no information. ANTI = reliably wrong (do NOT invert post hoc).")


if __name__ == "__main__":
    main()
