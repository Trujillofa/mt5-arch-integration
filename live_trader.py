#!/usr/bin/env python3
"""
Production-oriented XAUUSD intraday trader (BB/RSI pullback in uptrend).

- Risk ≤ 1% of balance ($100 on $10k) via ATR stop distance
- Every market order includes SL and TP
- Handles requotes / retcodes / disconnects

DO NOT auto-run against a live account from this goal.
Invoke explicitly:  python live_trader.py --once
                 or python live_trader.py --loop  (user review required)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PARAMS_PATH = Path(__file__).resolve().parent / "strategy_params.json"
LOG = logging.getLogger("live_trader")

# Defaults aligned with passing offline backtest
DEFAULT_PARAMS = {
    "mode": "bb_rsi",
    "rsi_buy": 30.0,
    "rsi_sell": 62.0,
    "sl_atr": 2.0,
    "tp_atr": 2.0,
    "bb_col": "bb_lo25",
    "trend_col": "ema200",
    "use_macd_filter": False,
    "hours": [12, 13, 14, 15, 16, 17, 18, 19, 20],
    "long_only": True,
    "risk_pct": 0.01,
    "cooldown": 2,
}

SYMBOL = "XAUUSD"
MAGIC = 26080601
MAX_RISK_FRAC = 0.01  # hard cap 1%
CONTRACT_SIZE = 100.0  # standard XAUUSD


@dataclass
class RiskSize:
    lots: float
    sl_price: float
    tp_price: float
    risk_dollars: float
    stop_distance: float


def load_params() -> dict[str, Any]:
    if PARAMS_PATH.is_file():
        data = json.loads(PARAMS_PATH.read_text())
        p = data.get("params") or {}
        # merge defaults for missing keys
        out = dict(DEFAULT_PARAMS)
        out.update(p)
        return out
    return dict(DEFAULT_PARAMS)


def size_position(
    *,
    balance: float,
    entry: float,
    side: int,
    atr: float,
    sl_atr: float,
    tp_atr: float,
    risk_pct: float = MAX_RISK_FRAC,
    contract_size: float = CONTRACT_SIZE,
    volume_min: float = 0.01,
    volume_max: float = 5.0,
    volume_step: float = 0.01,
    digits: int = 2,
) -> RiskSize:
    """
    Risk at most risk_pct of balance (capped at 1%) on ATR stop distance.
    side: +1 buy, -1 sell
    """
    if balance <= 0 or atr <= 0 or entry <= 0:
        raise ValueError("invalid balance/atr/entry")
    risk_pct = min(float(risk_pct), MAX_RISK_FRAC)
    risk_dollars = balance * risk_pct
    stop_distance = atr * sl_atr
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0")

    # loss ≈ stop_distance * contract_size * lots
    raw_lots = risk_dollars / (stop_distance * contract_size)
    # floor to volume_step (never round up past risk budget)
    steps = math.floor(raw_lots / volume_step + 1e-12)
    lots = steps * volume_step
    lots = min(volume_max, lots)
    lots = float(f"{lots:.2f}")

    # If even the broker minimum lot would risk more than risk_dollars, skip
    # (do not force volume_min — that overshoots the 1% cap on wide stops).
    min_lot_risk = stop_distance * contract_size * volume_min
    if lots < volume_min or min_lot_risk > risk_dollars + 1e-9:
        lots = 0.0

    if side > 0:
        sl = entry - stop_distance
        tp = entry + atr * tp_atr
    else:
        sl = entry + stop_distance
        tp = entry - atr * tp_atr

    sl = round(sl, digits)
    tp = round(tp, digits)
    return RiskSize(
        lots=lots,
        sl_price=sl,
        tp_price=tp,
        risk_dollars=risk_dollars,
        stop_distance=stop_distance,
    )


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def compute_signal_from_rates(df: pd.DataFrame, params: dict[str, Any]) -> int:
    """
    Return +1 long, -1 short, 0 flat using last completed bar (iloc[-2] if last is forming).
    """
    if len(df) < 220:
        return 0
    d = df.copy()
    c = d["close"].astype(float)
    h = d["high"].astype(float)
    l = d["low"].astype(float)
    d["ema200"] = _ema(c, 200)
    d["ema100"] = _ema(c, 100)
    d["ema50"] = _ema(c, 50)
    d["ema20"] = _ema(c, 20)
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    d["bb_mid"] = mid
    d["bb_lo"] = mid - 2.0 * sd
    d["bb_lo15"] = mid - 1.5 * sd
    d["bb_lo25"] = mid - 2.5 * sd
    d["bb_up"] = mid + 2.0 * sd
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-delta).clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - (100 / (1 + up / dn.replace(0, np.nan)))
    prev = c.shift(1)
    tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    # use last closed bar
    i = len(d) - 2
    row = d.iloc[i]
    hours = params.get("hours")
    if hours is not None:
        hr = pd.to_datetime(row["time"], utc=True).hour if "time" in d.columns else datetime.now(UTC).hour
        if int(hr) not in set(int(x) for x in hours):
            return 0
    trend_col = params.get("trend_col", "ema200")
    bb_col = params.get("bb_col", "bb_lo25")
    rsi_buy = float(params.get("rsi_buy", 30))
    if pd.isna(row["rsi"]) or pd.isna(row["atr"]) or pd.isna(row[trend_col]):
        return 0
    uptrend = float(row["close"]) > float(row[trend_col])
    if params.get("long_only", True) and not uptrend:
        return 0
    # bb reclaim
    if float(row["low"]) <= float(row[bb_col]) and float(row["close"]) > float(row[bb_col]):
        if float(row["close"]) < float(row["bb_mid"]) and float(row["rsi"]) <= rsi_buy + 10:
            return 1
    return 0


def try_mt5():
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5
    except ImportError:
        return None


def build_order_request(
    mt5: Any,
    *,
    symbol: str,
    side: int,
    lots: float,
    sl: float,
    tp: float,
    deviation: int = 30,
    magic: int = MAGIC,
    comment: str = "xau_bb_rsi",
) -> dict[str, Any]:
    """Build order_send dict — always includes SL and TP."""
    if sl <= 0 or tp <= 0:
        raise ValueError("SL and TP must both be set and > 0")
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"no tick for {symbol}")
    price = float(tick.ask if side > 0 else tick.bid)
    order_type = mt5.ORDER_TYPE_BUY if side > 0 else mt5.ORDER_TYPE_SELL
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lots),
        "type": order_type,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": int(deviation),
        "magic": int(magic),
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }


# Retcodes that often warrant a retry after refresh
RETRY_RETCODES = {
    10004,  # REQUOTE
    10006,  # REJECT
    10007,  # CANCEL
    10008,  # PLACED (sometimes intermediate)
    10012,  # TIMEOUT
    10020,  # PRICE_OFF / price changed
    10021,  # PRICE_CHANGED
    10024,  # TOO_MANY_REQUESTS
}


def send_order_with_retry(mt5: Any, request: dict[str, Any], max_retries: int = 3) -> Any:
    """order_send with requote/slippage-style retries and connection checks."""
    last = None
    for attempt in range(1, max_retries + 1):
        if not mt5.terminal_info():
            LOG.error("terminal_info None — connection drop; re-initialize")
            if not mt5.initialize():
                raise RuntimeError(f"re-init failed: {mt5.last_error()}")
        # refresh price on retry
        if attempt > 1:
            tick = mt5.symbol_info_tick(request["symbol"])
            if tick is None:
                time.sleep(0.5)
                continue
            request = dict(request)
            request["price"] = float(
                tick.ask if request["type"] == mt5.ORDER_TYPE_BUY else tick.bid
            )
            # ensure SL/TP still present
            if not request.get("sl") or not request.get("tp"):
                raise RuntimeError("refusing order without SL/TP")

        if not request.get("sl") or not request.get("tp"):
            raise RuntimeError("refusing order_send without both SL and TP")

        result = mt5.order_send(request)
        last = result
        if result is None:
            LOG.warning("order_send returned None: %s", mt5.last_error())
            time.sleep(0.4 * attempt)
            continue
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            LOG.info(
                "filled ticket=%s price=%s sl=%s tp=%s vol=%s",
                result.order,
                result.price,
                request["sl"],
                request["tp"],
                request["volume"],
            )
            return result
        ret = int(result.retcode)
        LOG.warning(
            "order_send attempt %s retcode=%s comment=%s",
            attempt,
            ret,
            getattr(result, "comment", ""),
        )
        if ret in RETRY_RETCODES or "requote" in str(getattr(result, "comment", "")).lower():
            time.sleep(0.35 * attempt)
            continue
        # hard fail
        break
    return last


def fetch_rates_df(mt5: Any, symbol: str, bars: int = 300) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"copy_rates_from_pos failed: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def has_open_position(mt5: Any, symbol: str, magic: int = MAGIC) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return False
    return any(int(p.magic) == magic for p in positions)


def run_once(*, dry_run: bool = True) -> int:
    params = load_params()
    mt5 = try_mt5()
    if mt5 is None:
        LOG.error("MetaTrader5 package not available on this platform")
        # Still demonstrate risk sizing offline for verification
        demo = size_position(
            balance=10_000,
            entry=2400.0,
            side=1,
            atr=5.0,
            sl_atr=float(params.get("sl_atr", 2.0)),
            tp_atr=float(params.get("tp_atr", 2.0)),
            risk_pct=float(params.get("risk_pct", 0.01)),
        )
        LOG.info(
            "dry sizing demo: lots=%s sl=%s tp=%s risk$=%.2f stop_dist=%.4f",
            demo.lots,
            demo.sl_price,
            demo.tp_price,
            demo.risk_dollars,
            demo.stop_distance,
        )
        return 2

    if not mt5.initialize():
        LOG.error("initialize failed: %s", mt5.last_error())
        return 1
    try:
        if not mt5.symbol_select(SYMBOL, True):
            LOG.error("symbol_select failed: %s", mt5.last_error())
            return 1
        info = mt5.symbol_info(SYMBOL)
        acc = mt5.account_info()
        if info is None or acc is None:
            LOG.error("symbol_info/account_info unavailable — connection issue")
            return 1

        if has_open_position(mt5, SYMBOL):
            LOG.info("already in position — skip")
            return 0

        df = fetch_rates_df(mt5, SYMBOL)
        signal = compute_signal_from_rates(df, params)
        LOG.info("signal=%s", signal)
        if signal == 0:
            return 0

        # ATR from last closed bar
        c = df["close"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        prev = c.shift(1)
        tr = pd.concat([(h - l), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
        atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-2])
        tick = mt5.symbol_info_tick(SYMBOL)
        entry = float(tick.ask if signal > 0 else tick.bid)

        risk = size_position(
            balance=float(acc.balance),
            entry=entry,
            side=signal,
            atr=atr,
            sl_atr=float(params.get("sl_atr", 2.0)),
            tp_atr=float(params.get("tp_atr", 2.0)),
            risk_pct=min(float(params.get("risk_pct", 0.01)), MAX_RISK_FRAC),
            contract_size=float(info.trade_contract_size or CONTRACT_SIZE),
            volume_min=float(info.volume_min or 0.01),
            volume_max=float(info.volume_max or 5.0),
            volume_step=float(info.volume_step or 0.01),
            digits=int(info.digits or 2),
        )
        if risk.lots <= 0:
            LOG.info(
                "skip: min lot would exceed 1%% risk (stop=%.4f risk$=%.2f)",
                risk.stop_distance,
                risk.risk_dollars,
            )
            return 0
        LOG.info(
            "size lots=%s sl=%s tp=%s risk$=%.2f (cap 1%% of balance)",
            risk.lots,
            risk.sl_price,
            risk.tp_price,
            risk.risk_dollars,
        )

        req = build_order_request(
            mt5,
            symbol=SYMBOL,
            side=signal,
            lots=risk.lots,
            sl=risk.sl_price,
            tp=risk.tp_price,
        )
        assert req["sl"] and req["tp"], "SL/TP required"

        if dry_run:
            LOG.info("DRY RUN — not sending: %s", {k: req[k] for k in req})
            return 0

        result = send_order_with_retry(mt5, req)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            LOG.error("order failed: %s", result)
            return 1
        return 0
    finally:
        mt5.shutdown()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    p = argparse.ArgumentParser(description="XAUUSD live trader (review before --live)")
    p.add_argument("--once", action="store_true", help="single evaluation cycle")
    p.add_argument("--loop", action="store_true", help="poll every N seconds")
    p.add_argument("--interval", type=int, default=60, help="loop interval seconds")
    p.add_argument(
        "--live",
        action="store_true",
        help="actually send orders (default is dry-run)",
    )
    args = p.parse_args(argv)

    if not args.once and not args.loop:
        # default safe: print sizing demo only
        LOG.info("No --once/--loop: dry sizing demo only (no orders).")
        return run_once(dry_run=True)

    dry = not args.live
    if args.live:
        LOG.warning("LIVE MODE — real orders will be sent")

    if args.once:
        return run_once(dry_run=dry)

    while True:
        try:
            run_once(dry_run=dry)
        except Exception:
            LOG.exception("loop iteration failed — will retry")
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    # Safety: never enter live loop unless user explicitly passes flags
    raise SystemExit(main())
