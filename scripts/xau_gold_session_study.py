#!/usr/bin/env python3
"""
xau_gold_session_study.py - test XAUUSD intraday hypotheses on M1 history.

RESEARCH ONLY / OFFLINE. Reads an M1 CSV, prints statistics, never trades.
Get data with scripts/fetch_m1_official_mcp.py (official MT5 MCP, read-only).

Three studies, all on the "trading day" London open -> 17:00 New York:

 1. TIMING   When does the day's extreme (the high on up days, the low on down
             days) form? Measured on UTC, London and New York clocks, against
             a null that keeps the sample's drift and each day's intraday
             volatility shape but randomises the direction of the moves. Signs are
             flipped in blocks (--null-block minutes, random phase) so short-range
             dependence in real M1 (bid/ask bounce, momentum bursts) survives.
             Every p-value is read off the null simulations themselves: a normal
             z-score on buckets the null almost never hits (the window's first
             minutes) reported z~+4 on a pure random walk. The best-window search
             reports a family-wise (max-statistic) p. Calibration on synthetic
             random walks: ~5% of p-values fall below 0.05.
             The clock whose peak stays put between summer and winter is the
             clock the effect actually follows.

 2. SWEEP    London range sweep and reclaim. Price breaks the London low (high)
             later in the day, then an M1 bar closes back inside within N
             minutes. Enter on that close, stop beyond the sweep wick, target
             London-anchored VWAP. Skipped when VWAP is behind the entry, and a
             trade already taken from another range that day is not counted
             twice.

 3. FADE     At fixed clock times, if price is stretched >= k x ATR(M15) from
             London VWAP, fade it back to VWAP, stop beyond the last hour's
             extreme.

 Trades run three ways (no breakeven, BE after +0.5R, BE halfway to target).
 Bars are bid prices; longs enter at ask and shorts exit at ask, so R is net of
 spread. MqlRates.spread is the *minimum* tick spread inside the bar, so this
 understates cost around news; the cost-sensitivity table adds slippage.
 A stop gapped through fills at the bar open, not at the stop.

WINDOW (research invariant, results/xau_holdout_lock.json)
  --window develop  (default) trading days before holdout_start. Explore here.
  --window holdout  evaluate a hypothesis that is already frozen. Do not iterate
                    on it: each look at the holdout spends it.
  --window all      both, flagged as contaminated.
  If a hypothesis (e.g. "the high forms 15:30-16:30 UTC") came from looking at
  charts of the develop period, only its holdout result is a real test.

SERVER TIME
  Default --server-tz ny-close (server = New York wall clock + 7h, i.e.
  GMT+2 winter / GMT+3 summer). When the CSV has a .meta.json from the MCP
  fetcher, the offset seen at fetch time is checked against it.

EXAMPLES
  python3 scripts/fetch_m1_official_mcp.py --from 2024-01-01 --to 2026-09-25
  python3 scripts/xau_gold_session_study.py --csv data/xauusd_m1_mcp.csv
  python3 scripts/xau_gold_session_study.py --csv data/xauusd_m1_mcp.csv --window holdout
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_LOCK = ROOT / "results" / "xau_holdout_lock.json"
COSTS_LOCK = ROOT / "results" / "xau_research_costs.json"

LON, NY = "Europe/London", "America/New_York"
CLOCKS = ("utc", "lon", "et")
CLOCK_NAMES = {"utc": "UTC", "lon": "London", "et": "New York"}
NB = 48  # 30-minute buckets per day
REGIMES = ("all", "summer", "winter", "mismatch")  # mismatch = UK/US DST out of step
VARIANTS = ("noBE", "BE_0.5R", "BE_halfway")

# pandas 2.3 on numpy >= 2.5 warns from inside Series +/- Timedelta; not ours.
warnings.filterwarnings("ignore", message="The 'generic' unit", category=DeprecationWarning)


def hhmm(s: str) -> int:
    h, m = s.strip().split(":")
    return int(h) * 60 + int(m)


def fmt(m: float) -> str:
    m = int(m) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


# --------------------------------------------------------------------- load
def load_csv(path: str, default_spread: float) -> pd.DataFrame:
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        first = fh.readline()
    sep = "\t" if "\t" in first else (";" if first.count(";") > first.count(",") else ",")
    raw = pd.read_csv(path, sep=sep)
    raw.columns = [c.strip().strip("<>").lower() for c in raw.columns]
    if "date" in raw.columns and "time" in raw.columns:
        ts = pd.to_datetime(raw["date"].astype(str).str.replace(".", "-", regex=False)
                            + " " + raw["time"].astype(str))
    elif "time" in raw.columns and np.issubdtype(raw["time"].dtype, np.number):
        ts = pd.to_datetime(raw["time"], unit="s")
    else:
        col = "datetime" if "datetime" in raw.columns else raw.columns[0]
        ts = pd.to_datetime(raw[col].astype(str).str.replace(".", "-", regex=False))
    vol = raw["tickvol"] if "tickvol" in raw.columns else raw.get("tick_volume", 1)
    spr = raw["spread"] if "spread" in raw.columns else default_spread
    df = pd.DataFrame({"server_time": ts, "open": raw["open"], "high": raw["high"],
                       "low": raw["low"], "close": raw["close"],
                       "tickvol": vol, "spread": spr})
    return df.sort_values("server_time").reset_index(drop=True)


def server_to_utc(ts: pd.Series, mode: str) -> pd.Series:
    if mode == "ny-close":  # server clock = New York wall clock + 7h
        ny = (ts - pd.Timedelta(hours=7)).dt.tz_localize(NY, ambiguous="NaT",
                                                         nonexistent="NaT")
        return ny.dt.tz_convert("UTC")
    if mode.startswith("fixed:"):
        return (ts - pd.Timedelta(hours=float(mode.split(":", 1)[1]))).dt.tz_localize("UTC")
    return ts.dt.tz_localize(mode, ambiguous="NaT",
                             nonexistent="NaT").dt.tz_convert("UTC")


def check_server_tz(csv: str, mode: str) -> None:
    """Warn when the fetcher saw a server offset the chosen --server-tz disagrees with."""
    meta_path = Path(f"{csv}.meta.json")
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text())
    seen, at = meta.get("server_utc_offset_h"), meta.get("fetched_at_utc")
    if seen is None or not at:
        return
    t = pd.Timestamp(at)
    if mode == "ny-close":
        want = t.tz_convert(NY).utcoffset().total_seconds() / 3600 + 7
    elif mode.startswith("fixed:"):
        want = float(mode.split(":", 1)[1])
    else:
        want = t.tz_convert(mode).utcoffset().total_seconds() / 3600
    if abs(want - seen) > 0.25:
        print(f"WARNING: --server-tz {mode} implies UTC{want:+g}h at {at}, but the terminal "
              f"reported UTC{seen:+g}h. Every clock in this study would be shifted.")


def holdout_start() -> pd.Timestamp:
    return pd.Timestamp(json.loads(HOLDOUT_LOCK.read_text())["holdout_start"])


def cost_sensitivity_points() -> list[float]:
    try:
        return [float(x) for x in json.loads(COSTS_LOCK.read_text())
                ["slippage_sensitivity_points_frozen"]]
    except (OSError, KeyError, ValueError):
        return [0.0, 5.0, 10.0, 20.0]


# ------------------------------------------------------------------ prepare
def prepare(df: pd.DataFrame, a) -> pd.DataFrame:
    df = df.copy()
    df["utc"] = server_to_utc(df["server_time"], a.server_tz)
    df = (df.dropna(subset=["utc"]).drop_duplicates("utc")
            .sort_values("utc").reset_index(drop=True))

    utc_w = df["utc"].dt.tz_localize(None)
    lon_w = df["utc"].dt.tz_convert(LON).dt.tz_localize(None)
    et_w = df["utc"].dt.tz_convert(NY).dt.tz_localize(None)
    for k, w in (("utc", utc_w), ("lon", lon_w), ("et", et_w)):
        df[f"{k}_min"] = (w.dt.hour * 60 + w.dt.minute).astype(int)

    # trading day ends 17:00 New York
    df["tday"] = (et_w + pd.Timedelta(hours=7)).dt.normalize()
    lon_day = lon_w.dt.normalize()
    us_dst = (et_w - utc_w) == pd.Timedelta(hours=-4)
    uk_dst = (lon_w - utc_w) == pd.Timedelta(hours=1)
    df["regime"] = np.select([us_dst & uk_dst, ~us_dst & ~uk_dst],
                             ["summer", "winter"], "mismatch")

    lon_open = hhmm(a.london_open)
    df["win"] = (lon_day == df["tday"]) & (df["lon_min"] >= lon_open)

    # VWAP anchored at London open (tick volume)
    typ = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["tickvol"].astype(float).clip(lower=1.0).where(df["win"], 0.0)
    num = (typ * vol).groupby(df["tday"]).cumsum()
    den = vol.groupby(df["tday"]).cumsum()
    df["vwap"] = (num / den.replace(0.0, np.nan)).where(df["win"])

    # ATR(14, Wilder) on M15, stamped at the M15 bar's close (no look-ahead)
    m15 = (df.set_index("utc")[["high", "low", "close"]]
             .resample("15min").agg({"high": "max", "low": "min", "close": "last"})
             .dropna())
    prev = m15["close"].shift()
    tr = pd.concat([m15["high"] - m15["low"], (m15["high"] - prev).abs(),
                    (m15["low"] - prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr_df = pd.DataFrame({"t": atr.index + pd.Timedelta(minutes=15),
                           "atr15": atr.to_numpy()})
    bars = pd.DataFrame({"t": df["utc"] + pd.Timedelta(minutes=1)})
    df["atr15"] = pd.merge_asof(bars, atr_df, on="t", direction="backward")["atr15"].to_numpy()

    # a zero or missing bar spread is unknown, not free: carry the last known one
    spr = pd.to_numeric(df["spread"], errors="coerce").where(lambda x: x > 0)
    df["spread_filled"] = spr.isna() & spr.ffill().notna()
    df["spread"] = spr.ffill().fillna(a.default_spread)
    df["spread_px"] = df["spread"] * a.point

    # study window, applied after indicators so ATR/VWAP warm up on earlier bars
    cut = holdout_start().tz_localize(None).normalize()
    if a.window == "develop":
        df["in_window"] = df["tday"] < cut
    elif a.window == "holdout":
        df["in_window"] = df["tday"] >= cut
    else:
        df["in_window"] = True
    return df


def trading_days(df: pd.DataFrame, min_bars: int):
    for tday, g in df[df["win"] & df["in_window"]].groupby("tday", sort=True):
        if len(g) >= min_bars:
            yield tday, g.reset_index(drop=True)


# ------------------------------------------------------------ trade engine
def simulate(side, entry, stop, target, op, hi, lo, cl, sp, be_trigger=None):
    """Bid bars. Stop is checked before target inside a bar (conservative); a
    bar that opens beyond the stop fills at its open.
    Returns (R, exit_reason, MFE_R, MAE_R, minutes_held)."""
    risk = abs(entry - stop)
    if risk <= 0 or len(hi) == 0:
        return np.nan, "none", np.nan, np.nan, 0
    cur, moved, mfe, mae = stop, False, 0.0, 0.0
    for t in range(len(hi)):
        if side > 0:
            fav, adv = hi[t] - entry, entry - lo[t]
            hit_stop = lo[t] <= cur
            fill = min(cur, op[t])
            hit_tgt = target is not None and hi[t] >= target
        else:
            fav, adv = entry - (lo[t] + sp[t]), (hi[t] + sp[t]) - entry
            hit_stop = hi[t] + sp[t] >= cur
            fill = max(cur, op[t] + sp[t])
            hit_tgt = target is not None and lo[t] + sp[t] <= target
        mae = max(mae, adv)
        if hit_stop:
            return side * (fill - entry) / risk, ("be" if moved else "stop"), mfe / risk, mae / risk, t + 1
        mfe = max(mfe, fav)
        if hit_tgt:
            return side * (target - entry) / risk, "target", mfe / risk, mae / risk, t + 1
        if be_trigger is not None and not moved and mfe >= be_trigger:
            cur, moved = entry, True
    exit_px = cl[-1] if side > 0 else cl[-1] + sp[-1]
    return side * (exit_px - entry) / risk, "time", mfe / risk, mae / risk, len(hi)


def run_variants(rec, side, entry, stop, target, g, k, a):
    """Simulate from the bar after k, capped by --horizon and the day end."""
    end = min(len(g), k + 1 + a.horizon)
    cols = [g[c].to_numpy()[k + 1:end] for c in ("open", "high", "low", "close", "spread_px")]
    risk = abs(entry - stop)
    extra = a.extra_cost_points * a.point / risk
    variants = {"noBE": None, "BE_0.5R": 0.5 * risk, "BE_halfway": 0.5 * abs(target - entry)}
    for name, trig in variants.items():
        r, why, mfe, mae, held = simulate(side, entry, stop, target, *cols, trig)
        rec[f"R_{name}"] = r - extra
        rec[f"exit_{name}"] = why
        if name == "noBE":
            rec.update(MFE_R=mfe, MAE_R=mae, minutes=held)
    return rec


# ------------------------------------------------------------ study 1: timing
def null_paths(o, c, n_null, block, rng, mu=0.0):
    """Synthetic paths for one day: M1 returns keep their size and their order
    inside `block`-bar blocks, but each block's deviation from the sample drift
    `mu` (price units per bar) gets a random sign; block edges have a random
    phase. mu must come from the whole sample, not from this day: a per-day mean
    makes the real deviations sum to zero (a bridge) while the null's do not."""
    r = np.diff(np.concatenate([[o], c]))
    n = len(r)
    dev = r - mu
    phase = rng.integers(0, block, size=(n_null, 1))
    blk = (np.arange(n)[None, :] + phase) // block
    signs = rng.choice([-1.0, 1.0], size=(n_null, n // block + 2))
    return np.cumsum(mu + dev * np.take_along_axis(signs, blk, axis=1), axis=1)


def sample_drift(days) -> float:
    """Average window return per bar as a fraction of the day's open."""
    net = sum((g["close"].iat[-1] - g["open"].iat[0]) / g["open"].iat[0] for _, g in days)
    return net / max(sum(len(g) for _, g in days), 1)


def timing_study(df, a, rng):
    """Returns per-day records and, per (clock, regime), (real counts, null counts
    per simulation). Null simulation j is a full synthetic sample of days."""
    rows = []
    real = {(k, r): np.zeros(NB, int) for k in CLOCKS for r in REGIMES}
    null = {(k, r): np.zeros((a.n_null, NB), int) for k in CLOCKS for r in REGIMES}
    sims = np.arange(a.n_null)
    days = list(trading_days(df, a.min_bars))
    mu_rel = sample_drift(days)
    for tday, g in days:
        o = g["open"].iat[0]
        c = g["close"].to_numpy()
        up = c[-1] > o
        i = int(np.argmax(c) if up else np.argmin(c))
        atr = g["atr15"].iat[i]
        reg = g["regime"].iat[0]
        rec = {"tday": tday.date(), "regime": reg, "dir": "up" if up else "down",
               "open": o, "close": c[-1], "extreme": c[i],
               "move_atr": abs(c[i] - o) / atr if atr > 0 else np.nan}
        p = null_paths(o, c, a.n_null, a.null_block, rng, mu_rel * o)
        idx = np.where(p[:, -1] > 0, p.argmax(axis=1), p.argmin(axis=1))
        for k in CLOCKS:
            mins = g[f"{k}_min"].to_numpy()
            rec[f"ext_{k}"] = int(mins[i])
            b = mins[idx] // 30
            for rg in ("all", reg):
                real[(k, rg)][mins[i] // 30] += 1
                np.add.at(null[(k, rg)], (sims, b), 1)
        rows.append(rec)
    stats = {key: (real[key], null[key]) for key in real if real[key].sum() > 0}
    return pd.DataFrame(rows), stats


def p_upper(real_value, null_values) -> float:
    """One-sided empirical p: share of null simulations at least as extreme."""
    return (1 + np.sum(null_values >= real_value)) / (1 + len(null_values))


def bucket_table(stats):
    out = []
    for (k, reg), (real, null) in stats.items():
        n = int(real.sum())
        mean, sd = null.mean(axis=0), null.std(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = (real - mean) / sd
        for b in range(NB):
            out.append({"clock": k, "regime": reg, "bucket": fmt(b * 30), "b": b,
                        "days": n, "real_n": int(real[b]), "real_share": real[b] / n,
                        "null_share": mean[b] / n, "excess": (real[b] - mean[b]) / n,
                        "z": z[b], "p": p_upper(real[b], null[:, b])})
    return pd.DataFrame(out)


def best_window(stats, clock, reg, width=4):
    """2h window (4 buckets) with the largest excess over the null, plus the
    family-wise p of that maximum (same scan run on every null simulation)."""
    if (clock, reg) not in stats:
        return None
    real, null = stats[(clock, reg)]
    n = real.sum()
    kern = np.ones(width, int)
    real_roll = np.convolve(real, kern, "valid")
    null_roll = np.array([np.convolve(row, kern, "valid") for row in null])
    centre = null_roll.mean(axis=0)
    ex_real = (real_roll - centre) / n
    ex_null = ((null_roll - centre) / n).max(axis=1)
    i = int(np.argmax(ex_real))
    return i * 30, ex_real[i], p_upper(ex_real[i], ex_null)


def parse_claim(spec: str):
    span, clock = spec.split("@")
    clock = clock.strip().lower()
    s, e = (hhmm(x) for x in span.split("-"))
    if clock not in CLOCKS or s % 30 or e % 30 or e <= s:
        sys.exit(f"--claim must be HH:MM-HH:MM@utc|lon|et on 30-minute edges: {spec}")
    return clock, list(range(s // 30, e // 30)), f"{fmt(s)}-{fmt(e)} {CLOCK_NAMES[clock]}"


def claim_test(stats, spec):
    clock, buckets, label = parse_claim(spec)
    rows = []
    for reg in ("all", "summer", "winter"):
        if (clock, reg) not in stats:
            continue
        real, null = stats[(clock, reg)]
        n = int(real.sum())
        r, nl = real[buckets].sum(), null[:, buckets].sum(axis=1)
        rows.append({"regime": reg, "days": n, "real_share": r / n,
                     "null_share": nl.mean() / n, "p": p_upper(r, nl)})
    return label, rows


def report_timing(days, stats, a):
    print("\n" + "=" * 78)
    print("1) WHEN DOES THE DAY'S EXTREME FORM?  (London open -> 17:00 NY, M1 closes)")
    print("=" * 78)
    cnt = days["regime"].value_counts().to_dict()
    print(f"days: {len(days)}  {cnt}   up: {(days['dir'] == 'up').sum()}  "
          f"down: {(days['dir'] == 'down').sum()}   null: {a.n_null} sims, "
          f"{a.null_block}-min sign blocks")

    print("\nClock test: 2-hour window where extremes beat the null the most, with its")
    print("family-wise p (the same best-window scan run on every null sample).")
    print("UTC vs local: the clock whose window does NOT move between summer and winter")
    print("is the one the effect follows. London vs New York only separate in the")
    print("'mismatch' weeks (March, late Oct) - a hint at most, the sample is small.\n")
    print(f"{'clock':<10}{'summer':>20}{'winter':>20}{'shift':>8}{'mismatch':>20}"
          f"{'all days':>22}")

    def cell(w):
        return f"{fmt(w[0])}-{fmt(w[0] + 120)} p={w[2]:.2f}" if w else "-"

    for k in CLOCKS:
        s, w, mm, al = (best_window(stats, k, r) for r in ("summer", "winter", "mismatch", "all"))
        sh = f"{(w[0] - s[0]) / 60:+.1f}h" if (s and w) else "-"
        alc = f"{al[1] * 100:+.1f}pp p={al[2]:.2f}" if al else "-"
        print(f"{CLOCK_NAMES[k]:<10}{cell(s):>20}{cell(w):>20}{sh:>8}{cell(mm):>20}{alc:>22}")

    label, rows = claim_test(stats, a.claim)
    print(f"\nPre-stated claim - extreme between {label}:")
    for r in rows:
        tag = "primary" if r["regime"] == "all" else "secondary"
        print(f"  {r['regime']:<7} {r['real_share'] * 100:5.1f}% of days vs "
              f"{r['null_share'] * 100:5.1f}% under the null   p={r['p']:.3f}  ({tag})")
    if a.window != "holdout":
        print("  (if this claim came from charts of this period, only --window holdout tests it)")

    print("\nTop 30-min buckets vs null, all days (per-bucket p, not corrected for "
          f"{NB * len(CLOCKS)} looks):")
    tab = bucket_table({k: v for k, v in stats.items() if k[1] == "all"})
    for k in CLOCKS:
        t = tab[tab["clock"] == k].nlargest(3, "excess")
        cells = [f"{r.bucket} {r.real_share * 100:.1f}% (null {r.null_share * 100:.1f}%, "
                 f"p {r.p:.3f})" for r in t.itertuples()]
        print(f"  {CLOCK_NAMES[k]:<9} " + " | ".join(cells))


# ------------------------------------------------------------- study 2: sweep
def sweep_study(df, a):
    refs = {}
    for spec in a.ref_windows.split(","):
        name, rng_ = spec.split("=")
        s, e = rng_.split("-")
        refs[name] = (hhmm(s), hhmm(e))
    buf = a.stop_buffer_points * a.point
    out = []
    for tday, g in trading_days(df, a.min_bars):
        lon = g["lon_min"].to_numpy()
        hi, lo = g["high"].to_numpy(), g["low"].to_numpy()
        cl, sp = g["close"].to_numpy(), g["spread_px"].to_numpy()
        taken: dict[tuple[int, int], str] = {}  # (side, entry bar) -> ref that took it
        for name, (s, e) in refs.items():
            ref = np.where((lon >= s) & (lon < e))[0]
            if len(ref) < 0.8 * (e - s):
                continue
            start = ref[-1] + 1
            if start >= len(g) - 5:
                continue
            for side in (+1, -1):
                level = lo[ref].min() if side > 0 else hi[ref].max()
                rec = {"tday": tday.date(), "regime": g["regime"].iat[0], "ref": name,
                       "side": "long@low" if side > 0 else "short@high", "level": level}
                brk = np.where(lo[start:] < level if side > 0 else hi[start:] > level)[0]
                if len(brk) == 0:
                    out.append({**rec, "status": "not_swept"})
                    continue
                j0 = start + brk[0]
                rec["sweep_et"] = fmt(g["et_min"].iat[j0])
                rec["sweep_utc"] = fmt(g["utc_min"].iat[j0])
                seg = np.arange(j0, min(j0 + a.reclaim_min, len(g) - 1))
                ok = seg[cl[seg] > level] if side > 0 else seg[cl[seg] < level]
                if len(ok) == 0:
                    out.append({**rec, "status": "swept_no_reclaim"})
                    continue
                k = int(ok[0])
                if side > 0:
                    entry = cl[k] + sp[k]
                    stop = lo[j0:k + 1].min() - buf
                else:
                    entry = cl[k]
                    stop = (hi[j0:k + 1] + sp[j0:k + 1]).max() + buf
                vw = g["vwap"].iat[k]
                risk = abs(entry - stop)
                rec.update(entry_utc=fmt(g["utc_min"].iat[k]), entry=entry, stop=stop,
                           target=vw, risk=risk)
                if np.isnan(vw) or (vw - entry) * side <= 0:
                    out.append({**rec, "status": "vwap_behind"})
                    continue
                rec["planned_R"] = abs(vw - entry) / risk
                if risk < a.min_risk_points * a.point:
                    out.append({**rec, "status": "risk_too_small"})
                    continue
                if (side, k) in taken:
                    out.append({**rec, "status": f"same_as_{taken[(side, k)]}"})
                    continue
                taken[(side, k)] = name
                rec["status"] = "traded"
                out.append(run_variants(rec, side, entry, stop, vw, g, k, a))
    return pd.DataFrame(out)


# -------------------------------------------------------------- study 3: fade
def parse_anchors(spec):
    res = []
    for item in spec.split(","):
        t, clock = item.strip().split("@")
        clock = clock.strip().lower()
        if clock not in CLOCKS:
            sys.exit(f"anchor clock must be utc, lon or et: {item}")
        res.append((f"{t}@{CLOCK_NAMES[clock]}", clock, hhmm(t)))
    return res


def fade_study(df, a):
    buf = a.stop_buffer_points * a.point
    anchors = parse_anchors(a.fade_times)
    out = []
    for tday, g in trading_days(df, a.min_bars):
        hi, lo = g["high"].to_numpy(), g["low"].to_numpy()
        cl, sp = g["close"].to_numpy(), g["spread_px"].to_numpy()
        for label, clock, m in anchors:
            idx = np.where(g[f"{clock}_min"].to_numpy() == (m - 1) % 1440)[0]
            if len(idx) == 0:
                continue
            i = int(idx[0])  # bar that closes at the anchor time
            atr, vw = g["atr15"].iat[i], g["vwap"].iat[i]
            if not (atr > 0) or np.isnan(vw):
                continue
            d = cl[i] - vw
            rec = {"tday": tday.date(), "regime": g["regime"].iat[0], "anchor": label,
                   "dist_atr": d / atr}
            if abs(d) < a.ext_atr * atr:
                out.append({**rec, "status": "not_extended"})
                continue
            side = -1 if d > 0 else +1
            lb = max(0, i - a.stop_lookback + 1)
            if side > 0:
                entry, stop = cl[i] + sp[i], lo[lb:i + 1].min() - buf
            else:
                entry, stop = cl[i], (hi[lb:i + 1] + sp[lb:i + 1]).max() + buf
            risk = abs(entry - stop)
            rec.update(side="long" if side > 0 else "short", entry=entry, stop=stop,
                       target=vw, risk=risk)
            if (vw - entry) * side <= 0:
                out.append({**rec, "status": "vwap_behind"})
                continue
            rec["planned_R"] = abs(vw - entry) / risk
            if risk < a.min_risk_points * a.point:
                out.append({**rec, "status": "risk_too_small"})
                continue
            rec["status"] = "traded"
            out.append(run_variants(rec, side, entry, stop, vw, g, i, a))
    return pd.DataFrame(out)


# ------------------------------------------------------------------ summary
def summarise(tr, by, min_planned):
    t = tr[tr["status"] == "traded"] if "status" in tr else tr.iloc[0:0]
    if t.empty:
        return pd.DataFrame()
    rows = []
    for key, g in t.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key, strict=True))
        r = g["R_noBE"]
        row["n"] = len(g)
        row["days"] = g["tday"].nunique()
        row["target%"] = (g["exit_noBE"] == "target").mean() * 100
        row["stop%"] = (g["exit_noBE"] == "stop").mean() * 100
        row["planR_med"] = g["planned_R"].median()
        for v in VARIANTS:
            row[f"avgR_{v}"] = g[f"R_{v}"].mean()
        row["t_noBE"] = r.mean() / (r.std(ddof=1) / math.sqrt(len(r))) if len(r) > 2 else np.nan
        good = g[g["planned_R"] >= min_planned]
        row[f"n_plan>={min_planned}"] = len(good)
        row[f"avgR_plan>={min_planned}"] = good["R_noBE"].mean() if len(good) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def cost_table(tr, by, a, pts):
    t = tr[tr["status"] == "traded"]
    rows = []
    for key, g in t.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key, strict=True))
        for p in pts:
            row[f"+{p:g}pt"] = (g["R_noBE"] - p * a.point / g["risk"]).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def report_trades(title, tr, by, a):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    if tr.empty:
        print("no data")
        return pd.DataFrame()
    st = tr.groupby(by + ["status"]).size().unstack(fill_value=0)
    print("setup counts:\n" + st.to_string())
    s = summarise(tr, by, a.min_planned_r)
    if s.empty:
        print("no trades")
        return s
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print("\nresults in R, net of spread"
              + (f" and {a.extra_cost_points:g} pts extra cost" if a.extra_cost_points else "")
              + " (avgR = expectancy per trade, t = t-stat of avgR_noBE):")
        print(s.round(2).to_string(index=False))
        pts = cost_sensitivity_points()
        print(f"\navgR_noBE with extra slippage per round trip (points, "
              f"{COSTS_LOCK.name} sensitivity set):")
        print(cost_table(tr, by, a, pts).round(2).to_string(index=False))
    cells = len(s) * len(VARIANTS) + len(s)
    print(f"\n{cells} numbers above are expectancy estimates on one sample. At |t|>2, about "
          f"{cells * 0.05:.1f} would clear by chance with no edge anywhere.")
    return s


# --------------------------------------------------------------------- plot
def plot_timing(tab, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharey=True)
    for ax, k in zip(axes, CLOCKS, strict=True):
        for reg, style in (("summer", "-"), ("winter", "--")):
            t = tab[(tab["clock"] == k) & (tab["regime"] == reg)].sort_values("b")
            if not t.empty:
                ax.plot(t["b"] * 0.5, t["excess"] * 100, style, label=reg)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title(f"Day's extreme vs null - {CLOCK_NAMES[k]} clock")
        ax.set_ylabel("excess, pp")
        ax.set_xticks(range(0, 25, 2))
        ax.set_xlim(0, 24)
        ax.legend(loc="upper left")
    axes[-1].set_xlabel("hour of day on that clock")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    return path


# --------------------------------------------------------------------- main
def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="M1 CSV (MT5 export layout)")
    ap.add_argument("--window", choices=("develop", "holdout", "all"), default="develop")
    ap.add_argument("--server-tz", default="ny-close",
                    help="ny-close | fixed:+2 | IANA zone (default ny-close)")
    ap.add_argument("--point", type=float, default=0.01, help="price point (gold 0.01)")
    ap.add_argument("--default-spread", type=float, default=30,
                    help="points, used if the CSV has no spread column")
    ap.add_argument("--london-open", default="08:00", help="London wall time")
    ap.add_argument("--min-bars", type=int, default=700,
                    help="skip trading days with fewer M1 bars (holidays, gaps)")
    ap.add_argument("--n-null", type=int, default=500, help="null simulations")
    ap.add_argument("--null-block", type=int, default=30,
                    help="minutes per sign-flip block in the null")
    ap.add_argument("--claim", default="15:30-16:30@utc",
                    help="pre-stated extreme window to test, HH:MM-HH:MM@utc|lon|et")
    ap.add_argument("--ref-windows", default="LDN_AM=08:00-13:00,LDN_FULL=08:00-16:00",
                    help="London-time ranges whose low/high get swept")
    ap.add_argument("--reclaim-min", type=int, default=15,
                    help="minutes allowed between first break and reclaim close")
    ap.add_argument("--fade-times",
                    default="15:00@utc,16:00@utc,17:00@utc,15:00@lon,16:00@lon,11:00@et,12:00@et")
    ap.add_argument("--ext-atr", type=float, default=1.0,
                    help="fade only if |price - VWAP| >= this x ATR(M15)")
    ap.add_argument("--stop-lookback", type=int, default=60,
                    help="fade stop beyond this many minutes' extreme")
    ap.add_argument("--stop-buffer-points", type=float, default=20)
    ap.add_argument("--min-risk-points", type=float, default=100,
                    help="skip trades whose stop is closer than this")
    ap.add_argument("--horizon", type=int, default=180, help="max minutes in a trade")
    ap.add_argument("--extra-cost-points", type=float, default=0,
                    help="slippage/commission per round trip, in points")
    ap.add_argument("--min-planned-r", type=float, default=1.5)
    ap.add_argument("--out", default="results/xau_gold_session_study")
    ap.add_argument("--seed", type=int, default=7)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    check_server_tz(a.csv, a.server_tz)
    df = prepare(load_csv(a.csv, a.default_spread), a)
    print(f"bars: {len(df):,}  {df['utc'].iat[0]:%Y-%m-%d} -> {df['utc'].iat[-1]:%Y-%m-%d} UTC"
          f"  point={a.point}  median spread={df['spread'].median():g} pts"
          f" ({df['spread_filled'].sum():,} bars carried forward)"
          f"  window={a.window} (holdout_start {holdout_start():%Y-%m-%d})")
    if a.window == "all":
        print("WARNING: --window all mixes develop and holdout days; nothing here is out of sample.")

    out = Path(a.out) / a.window
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(a.seed)

    days, stats = timing_study(df, a, rng)
    if days.empty:
        sys.exit(f"No complete trading days in the {a.window} window. Check the CSV range, "
                 "--server-tz, --london-open, --min-bars.")
    tab = bucket_table(stats)
    report_timing(days, stats, a)

    sw = sweep_study(df, a)
    s_sum = report_trades("2) LONDON RANGE SWEEP + RECLAIM -> VWAP", sw, ["ref", "side"], a)

    fd = fade_study(df, a)
    f_sum = report_trades(f"3) FADE EXTENSION >= {a.ext_atr:g} ATR(M15) FROM LONDON VWAP",
                          fd, ["anchor"], a)

    days.to_csv(out / "days.csv", index=False)
    tab.to_csv(out / "timing_buckets.csv", index=False)
    sw.to_csv(out / "sweep_trades.csv", index=False)
    fd.to_csv(out / "fade_trades.csv", index=False)
    s_sum.to_csv(out / "sweep_summary.csv", index=False)
    f_sum.to_csv(out / "fade_summary.csv", index=False)
    png = plot_timing(tab, out / "extreme_timing.png")
    print(f"\nfiles in {out}" + (f"  (chart: {Path(png).name})" if png else ""))


if __name__ == "__main__":
    main()
