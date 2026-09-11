"""btc_trend_pullback_core — offline mirror of BtcTrendPullback.mq5 (H1 chart + H4 bias).

First lock/PF for the only mt5-arch indicator with zero offline evidence.
Freeze-before-peek: this module mirrors the *shipped* indicator grammar
(``mql5/Indicators/BtcTrendPullback.mq5`` v1.00 defaults); nothing here may
be tuned after looking at PnL — the lock owns every number.

Causality rules (indicator-mirrored):
- H4 bias at chart bar ``i`` uses the last **completed** H4 bar only
  (``CompletedHtfShift`` semantics: if bar-i's close time is inside an H4
  bucket, the previous H4 bucket is the completed one).
- Signals fire on the close of bar ``i`` only; the forming bar never signals.
- Edge trigger: a signal fires only if the previous bar did not also signal.

Book: FP Markets BTCUSD H1 ``cache/H1.hc`` (offline read_mt5_hc; the terminal
is never touched). Clock: server wall − 7h → America/New_York (admitted
lag-0 vs Binance UTC; see the lock). Spread imputation mirrors BTC-NY.

Run with plain python3 (host numpy/pandas), never uv run.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import lane_kit as lk  # noqa: E402

ROOT = _SCRIPTS.parent

DATA_DIR = ROOT / "results" / "btc_trend_pullback_data"
CSV_NAME = "history_BTCUSD_H1.csv"
LOCK_PATH = ROOT / "results" / "btc_trend_pullback_lock.json"
DEFAULT_HC = (
    Path.home()
    / ".mt5-fpmarkets/drive_c/Program Files/FP Markets MT5 Terminal/Bases/FPMarketsSC-Live/history/BTCUSD/cache/H1.hc"
)


def export_h1_csv(hc_path: Path = DEFAULT_HC, out_dir: Path = DATA_DIR) -> Path:
    """Dump the FP H1 cache to the gitignored CSV book (offline; terminal untouched).

    Same pattern as the BTC-NY lane: the lock pins the CSV sha256, so a
    longer live cache is a new book — rerun the screen only after re-locking.
    """
    from us_index_session_backtest import hc_to_export_csv  # noqa: E402

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / CSV_NAME
    hc_to_export_csv(Path(hc_path), out, symbol="BTCUSD")
    return out


# Indicator-mirrored constants (BtcTrendPullback.mq5 v1.00 defaults).
# Lane-local frozen values — do not retune; the lock pins them.
SERVER_MINUS_HOURS = 7
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
MIN_TREND_STRENGTH_PCT = 0.01
STRONG_TREND_STRENGTH_PCT = 0.015
RSI_RECLAIM = 50.0
CONTINUATION_RSI = 54.0
MAX_PULLBACK_PCT = 0.015
MAX_EMA50_EXTENSION_PCT = 0.03
PANIC_RSI = 35.0
PANIC_ATR_PCT = 0.08

FAMILIES = (
    "btc_h4bias_h1_pullback_reclaim",
    "btc_h4bias_h1_continuation",
    "btc_h4bias_h1_full_grammar",
)
A_PRIORI_FAMILY = "btc_h4bias_h1_full_grammar"

TAKEN_HOLDOUTS = (
    date(2025, 3, 1),
    date(2026, 1, 1),
    date(2026, 3, 1),
    date(2026, 6, 1),
    date(2026, 7, 1),
)


@dataclass
class H1Book:
    """Causal H1 bundle. Arrays are chronologically ordered (index 0 oldest)."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    spread: np.ndarray
    server_epoch: np.ndarray
    et_key: np.ndarray
    et_date: np.ndarray  # object array of date
    atr: np.ndarray
    ema50: np.ndarray
    ema200: np.ndarray
    rsi: np.ndarray
    macd_hist: np.ndarray
    h4_bias: np.ndarray
    h4_strength: np.ndarray


def et_from_server(server_naive: pd.Series) -> pd.Series:
    """Server wall − 7h → America/New_York; DST fold (NaT) bars are dropped.

    Same rule as scripts/btc_ny_session_scalp_core.py (BTC-NY lock `clock`).
    Never the constant-10800 UTC offset (mislabels every US-winter bar).
    """
    shifted = server_naive - pd.Timedelta(hours=SERVER_MINUS_HOURS)
    et = shifted.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    return et


def load_btc_h1(
    csv_path: Path,
    *,
    expected_sha256: str | None = None,
    min_trend_strength_pct: float = MIN_TREND_STRENGTH_PCT,
) -> H1Book:
    """Load the exported H1 CSV, verify its sha, impute spreads, build indicators."""
    if expected_sha256 is not None:
        lk.verify_data_sha256(csv_path, expected_sha256)
    df = pd.read_csv(csv_path)
    server = pd.to_datetime(df["server_epoch"], unit="s")
    et = et_from_server(server)
    keep = et.notna()
    df = df.loc[keep].reset_index(drop=True)
    et = et.loc[keep].reset_index(drop=True)

    o = df["open"].astype(float).to_numpy()
    h = df["high"].astype(float).to_numpy()
    lo = df["low"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    spr = df["spread"].astype(float).to_numpy()

    # Zero-spread imputation (BTC-NY rule): forward-fill within the same ET
    # day, else the global median.
    et_key = (et.dt.year * 10000 + et.dt.month * 100 + et.dt.day).to_numpy()
    et_date = et.dt.date.to_numpy()
    if (spr <= 0).any():
        med = float(np.median(spr[spr > 0])) if (spr > 0).any() else 0.0
        last_ok: dict[int, float] = {}
        for i in range(len(spr)):
            if spr[i] <= 0:
                spr[i] = last_ok.get(int(et_key[i]), med)
            else:
                last_ok[int(et_key[i])] = float(spr[i])

    return rebuild_indicators(
        H1Book(
            open=o,
            high=h,
            low=lo,
            close=c,
            spread=spr,
            server_epoch=df["server_epoch"].to_numpy(),
            et_key=et_key.astype(np.int64),
            et_date=et_date,
            atr=np.array([]),
            ema50=np.array([]),
            ema200=np.array([]),
            rsi=np.array([]),
            macd_hist=np.array([]),
            h4_bias=np.array([]),
            h4_strength=np.array([]),
        ),
        min_trend_strength_pct=min_trend_strength_pct,
    )


def rebuild_indicators(
    b: H1Book, *, min_trend_strength_pct: float = MIN_TREND_STRENGTH_PCT
) -> H1Book:
    """Recompute ATR/EMA/RSI/MACD/H4 bias from current OHLC (null-rotation path)."""
    atr = _wilder_atr(b.high, b.low, b.close, 14)
    ema50 = _ema(b.close, EMA_FAST)
    ema200 = _ema(b.close, EMA_SLOW)
    rsi = _wilder_rsi(b.close, RSI_PERIOD)
    macd_hist = _macd_hist(b.close)
    bias, strength = _h4_bias_completed(b.server_epoch, b.close, min_trend_strength_pct)
    return H1Book(
        open=b.open,
        high=b.high,
        low=b.low,
        close=b.close,
        spread=b.spread,
        server_epoch=b.server_epoch,
        et_key=b.et_key,
        et_date=b.et_date,
        atr=atr,
        ema50=ema50,
        ema200=ema200,
        rsi=rsi,
        macd_hist=macd_hist,
        h4_bias=bias,
        h4_strength=strength,
    )


# ---------------------------------------------------------------------------
# Indicator math (chronological, index 0 oldest — mirrors us_index_session_core)
# ---------------------------------------------------------------------------


def _ema(price: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(price), np.nan)
    if len(price) < period or period < 1:
        return out
    seed = float(np.mean(price[:period]))
    out[period - 1] = seed
    mult = 2.0 / (period + 1.0)
    for i in range(period, len(price)):
        out[i] = price[i] * mult + out[i - 1] * (1.0 - mult)
    return out


def _wilder_atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, period: int) -> np.ndarray:
    n = len(c)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    tr = np.empty(n)
    tr[0] = h[0] - lo[0]
    for i in range(1, n):
        tr[i] = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
    out[period] = float(np.mean(tr[1 : period + 1]))
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def _wilder_rsi(c: np.ndarray, period: int) -> np.ndarray:
    n = len(c)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    d = np.diff(c)
    pos = np.where(d > 0, d, 0.0)
    neg = np.where(d < 0, -d, 0.0)
    avg_pos = float(np.mean(pos[:period]))
    avg_neg = float(np.mean(neg[:period]))
    out[period] = _rsi_val(avg_pos, avg_neg)
    for i in range(period + 1, n):
        avg_pos = (avg_pos * (period - 1) + pos[i - 1]) / period
        avg_neg = (avg_neg * (period - 1) + neg[i - 1]) / period
        out[i] = _rsi_val(avg_pos, avg_neg)
    return out


def _rsi_val(avg_pos: float, avg_neg: float) -> float:
    if avg_neg == 0.0:
        return 50.0 if avg_pos == 0.0 else 100.0
    return 100.0 - (100.0 / (1.0 + avg_pos / avg_neg))


def _macd_hist(c: np.ndarray) -> np.ndarray:
    """MT5 iMACD mirror: macd = EMA12-EMA26; signal = **SMA9** of macd (MT5
    uses SMA for the signal line, unlike MT4); hist = macd - signal."""
    e12 = _ema(c, MACD_FAST)
    e26 = _ema(c, MACD_SLOW)
    macd = e12 - e26
    n = len(c)
    signal = np.full(n, np.nan)
    v0 = MACD_SLOW - 1  # first valid macd index
    if n > v0 + MACD_SIGNAL:
        for i in range(v0 + MACD_SIGNAL - 1, n):
            signal[i] = float(np.mean(macd[i - MACD_SIGNAL + 1 : i + 1]))
    return macd - signal


def _h4_bias_completed(
    server_epoch: np.ndarray,
    close: np.ndarray,
    min_strength_pct: float,
) -> tuple[np.ndarray, np.ndarray]:
    """H4 EMA50/200 bias from **completed** H4 bars only (CompletedHtfShift mirror).

    The indicator tests containment with the chart bar's **open** time
    (``open_t + 14400 > chart_time -> still inside -> shift + 1``), so a bar
    NEVER reads its own containing bucket: it always uses the previous
    completed bucket (conservative by one H1 bar — mirrors the shipped
    indicator exactly). H4 buckets align to server midnight (MT5 convention).
    """
    n = len(close)
    bias = np.zeros(n, dtype=int)
    strength = np.zeros(n)
    epoch = server_epoch.astype(np.int64)
    bucket_open = (epoch // 14400) * 14400
    completed_bucket = bucket_open - 14400

    uniq = np.unique(completed_bucket)
    idx_of: dict[int, int] = {int(bk): i for i, bk in enumerate(uniq)}
    order = np.argsort(bucket_open, kind="stable")
    bs = bucket_open[order]
    starts = np.searchsorted(bs, uniq, side="left")
    ends = np.searchsorted(bs, uniq, side="right")
    h4_close = np.empty(len(uniq))
    for k in range(len(uniq)):
        s, e = starts[k], ends[k]
        h4_close[k] = close[order][e - 1]
    e50 = _ema(h4_close, EMA_FAST)
    e200 = _ema(h4_close, EMA_SLOW)
    for i in range(n):
        k = idx_of[int(completed_bucket[i])]
        if not (np.isfinite(e50[k]) and np.isfinite(e200[k])) or e200[k] <= 0:
            continue
        s = (e50[k] - e200[k]) / e200[k]
        if h4_close[k] > e200[k] and e50[k] > e200[k] and s >= min_strength_pct:
            bias[i] = 1
        elif h4_close[k] < e200[k] and e50[k] < e200[k] and (-s) >= min_strength_pct:
            bias[i] = -1
        strength[i] = s
    return bias, strength


# ---------------------------------------------------------------------------
# Signal families — faithful mirrors of BtcTrendPullback.mq5 setups
# ---------------------------------------------------------------------------


def _setup_pullback_long(b: H1Book, i: int) -> bool:
    if not np.isfinite(b.rsi[i]) or not np.isfinite(b.macd_hist[i]):
        return False
    if b.ema50[i] <= 0:
        return False
    dist = abs(b.close[i] - b.ema50[i]) / b.ema50[i]
    if dist > MAX_PULLBACK_PCT:
        return False
    recovery = (
        b.rsi[i] >= RSI_RECLAIM
        and b.rsi[i] > b.rsi[i - 1]
        and b.macd_hist[i] >= 0.0
        and b.macd_hist[i] > b.macd_hist[i - 1]
        and b.close[i] > b.close[i - 1]
    )
    return recovery


def _setup_pullback_short(b: H1Book, i: int) -> bool:
    if not np.isfinite(b.rsi[i]) or not np.isfinite(b.macd_hist[i]):
        return False
    if b.ema50[i] <= 0:
        return False
    dist = abs(b.close[i] - b.ema50[i]) / b.ema50[i]
    if dist > MAX_PULLBACK_PCT:
        return False
    recovery = (
        b.rsi[i] <= (100.0 - RSI_RECLAIM)
        and b.rsi[i] < b.rsi[i - 1]
        and b.macd_hist[i] <= 0.0
        and b.macd_hist[i] < b.macd_hist[i - 1]
        and b.close[i] < b.close[i - 1]
    )
    return recovery


def _panic_veto(b: H1Book, i: int, atr_pct: float, side: int) -> bool:
    stress = (b.rsi[i] <= PANIC_RSI) or (atr_pct >= PANIC_ATR_PCT)
    if side > 0:
        return bool(np.isfinite(b.rsi[i])) and stress and (b.close[i] < b.ema200[i])
    stress_s = (b.rsi[i] >= (100.0 - PANIC_RSI)) or (atr_pct >= PANIC_ATR_PCT)
    return bool(np.isfinite(b.rsi[i])) and stress_s and (b.close[i] > b.ema200[i])


def _setup_continuation(b: H1Book, i: int, side: int) -> bool:
    if not np.isfinite(b.rsi[i]) or not np.isfinite(b.macd_hist[i]):
        return False
    if b.ema50[i] <= 0:
        return False
    strong = (
        (b.h4_strength[i] >= STRONG_TREND_STRENGTH_PCT)
        if side > 0
        else ((-b.h4_strength[i]) >= STRONG_TREND_STRENGTH_PCT)
    )
    ext = (b.close[i] - b.ema50[i]) / b.ema50[i]
    not_ext = (
        (ext >= 0.0 and ext <= MAX_EMA50_EXTENSION_PCT)
        if side > 0
        else (-ext >= 0.0 and -ext <= MAX_EMA50_EXTENSION_PCT)
    )
    above = (b.close[i] >= b.ema50[i]) if side > 0 else (b.close[i] <= b.ema50[i])
    if side > 0:
        mom = (b.rsi[i] >= CONTINUATION_RSI) and (
            b.rsi[i] > b.rsi[i - 1] or b.macd_hist[i] > b.macd_hist[i - 1]
        )
    else:
        mom = (b.rsi[i] <= (100.0 - CONTINUATION_RSI)) and (
            b.rsi[i] < b.rsi[i - 1] or b.macd_hist[i] < b.macd_hist[i - 1]
        )
    return strong and above and not_ext and mom


def family_signals(
    b: H1Book,
    family: str,
    *,
    min_atr_pct: float = 0.01,
    long_only: bool = False,
    one_per_day: bool = True,
    edge_trigger: bool = True,
) -> np.ndarray:
    """Signal array (+1/-1/0) on the close of bar i. Forming bar never signals."""
    if family not in FAMILIES:
        raise SystemExit(f"unknown family {family!r}")
    n = len(b.close)
    raw = np.zeros(n, dtype=int)

    for i in range(1, n - 1):  # never the forming bar (last index)
        if not (np.isfinite(b.atr[i]) and b.close[i] > 0 and b.atr[i] > 0):
            continue
        atr_pct = b.atr[i] / b.close[i]
        if atr_pct < min_atr_pct:
            continue
        bias = int(b.h4_bias[i])
        if bias == 0:
            continue
        side = bias  # mirrored stack: trade with the H4 bias only
        if long_only and side < 0:
            continue
        if _panic_veto(b, i, atr_pct, side):
            continue
        fired = False
        if family == "btc_h4bias_h1_pullback_reclaim":
            fired = _setup_pullback_long(b, i) if side > 0 else _setup_pullback_short(b, i)
        elif family == "btc_h4bias_h1_continuation":
            fired = _setup_continuation(b, i, side)
        else:  # full_grammar — the shipped default: pullback OR continuation
            fired = (
                _setup_pullback_long(b, i) if side > 0 else _setup_pullback_short(b, i)
            ) or _setup_continuation(b, i, side)
        if fired:
            raw[i] = side

    if one_per_day:
        raw = _dedupe_one_per_day(raw, b.et_key)
    if edge_trigger:
        raw = _edge_trigger(raw)
    return raw


def _dedupe_one_per_day(raw: np.ndarray, et_key: np.ndarray) -> np.ndarray:
    out = np.zeros_like(raw)
    seen: set[int] = set()
    for i in range(len(raw)):
        if raw[i] == 0:
            continue
        k = int(et_key[i])
        if k in seen:
            continue
        seen.add(k)
        out[i] = raw[i]
    return out


def _edge_trigger(raw: np.ndarray) -> np.ndarray:
    out = np.zeros_like(raw)
    for i in range(1, len(raw)):
        if raw[i] != 0 and raw[i - 1] == 0:
            out[i] = raw[i]
    return out


def holdout_split_et_date(et_date: np.ndarray, holdout_start: date) -> np.ndarray:
    """Boolean mask: bar belongs to develop (< holdout) or holdout (>=)."""
    return np.array([d >= holdout_start for d in et_date])
