#!/usr/bin/env python3
"""Published-spec reconstruction of Grid Scalper MA defaults — ruin study.

NOT the Market .ex5. NOT a family_id. Frozen lock:
results/grid_scalper_ma_ruin_lock.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LOCK = {
    "product": "Market 133466 Grid Scalper MA MT5 EA v11.48",
    "kind": "published_spec_reconstruction",
    "not_market_ex5": True,
    "family_id": None,
    "window": ["2024-03-01", "2024-04-01"],
    "symbol": "XAUUSD",
    "timeframe": "M15",
    "deposit": 10000.0,
    "leverage": 100,
    "point": 0.01,
    "usd_per_point_per_lot": 1.0,
    "grid_price": 11.0,
    "first_tp_price": 11.0,
    "breakeven_buffer": 0.05,
    "multiplier": 1.5,
    "start_lot": 0.01,
    "ma_period": 21,
    "stop_loss": False,
    "basket_cap": None,
    "daily_dd": False,
    "stopout_margin_level_pct": 50.0,
}

REPO = Path(__file__).resolve().parents[1]
CSV = REPO / "xauusd_data.csv"
OUT = REPO / "results" / "grid_scalper_ma_ruin_2024-03.json"


def pnl_usd(delta_price: float, lots: float) -> float:
    return (delta_price / LOCK["point"]) * LOCK["usd_per_point_per_lot"] * lots


def main() -> None:
    df = pd.read_csv(CSV, parse_dates=["time"])
    m15 = df[df["timeframe"] == "M15"].sort_values("time").reset_index(drop=True)
    sl = m15[(m15["time"] >= LOCK["window"][0]) & (m15["time"] < LOCK["window"][1])].copy()
    sl["sma"] = sl["close"].rolling(LOCK["ma_period"], min_periods=LOCK["ma_period"]).mean()

    equity = LOCK["deposit"]
    peak = equity
    max_dd = 0.0
    max_lots = 0.0
    max_levels = 0
    stopout = False
    stopout_time = None
    closed = []
    basket = None  # dict | None

    def close_basket(price: float, t, reason: str) -> None:
        nonlocal equity, basket, peak, max_dd
        if basket is None:
            return
        net = 0.0
        sign = 1 if basket["side"] == "buy" else -1
        for pos in basket["pos"]:
            net += pnl_usd((price - pos["price"]) * sign, pos["lots"])
        equity += net
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        closed.append(
            {
                "time": str(t),
                "reason": reason,
                "n": len(basket["pos"]),
                "lots": round(sum(p["lots"] for p in basket["pos"]), 4),
                "net": round(net, 2),
                "equity": round(equity, 2),
            }
        )
        basket = None

    def margin_usd(price: float, lots: float) -> float:
        return abs(price) * 100.0 * lots / LOCK["leverage"]

    for i, row in sl.iterrows():
        if pd.isna(row["sma"]) or i == sl.index[0]:
            continue
        prev = sl.loc[i - 1]
        t, o, h, l, c = row["time"], row["open"], row["high"], row["low"], row["close"]
        spread_px = float(row["spread"]) * LOCK["point"]

        if basket is None:
            crossed_up = prev["close"] <= prev["sma"] and c > row["sma"]
            crossed_dn = prev["close"] >= prev["sma"] and c < row["sma"]
            if crossed_up or crossed_dn:
                side = "buy" if crossed_up else "sell"
                fill = c + spread_px / 2 if side == "buy" else c - spread_px / 2
                basket = {
                    "side": side,
                    "pos": [{"price": fill, "lots": LOCK["start_lot"]}],
                }
            continue

        side = basket["side"]
        last = basket["pos"][-1]["price"]
        # Adverse grid adds from bar extremes (M15 OHLC proxy).
        added = False
        if side == "buy":
            while last - l >= LOCK["grid_price"] - 1e-9:
                last = last - LOCK["grid_price"]
                nxt = round(basket["pos"][-1]["lots"] * LOCK["multiplier"], 4)
                basket["pos"].append({"price": last - spread_px / 2, "lots": nxt})
                added = True
        else:
            while h - last >= LOCK["grid_price"] - 1e-9:
                last = last + LOCK["grid_price"]
                nxt = round(basket["pos"][-1]["lots"] * LOCK["multiplier"], 4)
                basket["pos"].append({"price": last + spread_px / 2, "lots": nxt})
                added = True

        lots = sum(p["lots"] for p in basket["pos"])
        max_lots = max(max_lots, lots)
        max_levels = max(max_levels, len(basket["pos"]))

        # Mark-to-market at close for stop-out.
        mtm = 0.0
        for pos in basket["pos"]:
            sign = 1 if side == "buy" else -1
            mtm += pnl_usd((c - pos["price"]) * sign, pos["lots"])
        eq = equity + mtm
        mar = margin_usd(c, lots)
        ml = (eq / mar * 100.0) if mar > 0 else 999.0
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        if ml < LOCK["stopout_margin_level_pct"] or eq <= 0:
            close_basket(c, t, "stopout")
            stopout = True
            stopout_time = str(t)
            break

        # High and low of the same bar have no order. Taking TP/BE off the
        # favorable extreme after adding from the adverse one invents a close
        # and understates ruin. Close is last, so the stop-out check above stays.
        if added:
            continue

        vwap = sum(p["price"] * p["lots"] for p in basket["pos"]) / lots
        if len(basket["pos"]) == 1:
            tgt = basket["pos"][0]["price"] + (
                LOCK["first_tp_price"] if side == "buy" else -LOCK["first_tp_price"]
            )
            hit = h >= tgt if side == "buy" else l <= tgt
            if hit:
                close_basket(tgt, t, "first_tp")
        else:
            be = vwap + (LOCK["breakeven_buffer"] if side == "buy" else -LOCK["breakeven_buffer"])
            hit = h >= be if side == "buy" else l <= be
            if hit:
                close_basket(be, t, "basket_be")

    if basket is not None and not stopout:
        last_row = sl.iloc[-1]
        close_basket(float(last_row["close"]), last_row["time"], "window_end")

    wins = [x for x in closed if x["net"] > 0]
    losses = [x for x in closed if x["net"] <= 0]
    report = {
        "lock": LOCK,
        "bars": int(len(sl)),
        "price_low": float(sl["low"].min()),
        "price_high": float(sl["high"].max()),
        "stopout": stopout,
        "stopout_time": stopout_time,
        "final_equity": round(equity, 2),
        "max_dd_usd": round(max_dd, 2),
        "max_dd_pct_of_deposit": round(100.0 * max_dd / LOCK["deposit"], 2),
        "max_concurrent_lots": round(max_lots, 4),
        "max_grid_levels": max_levels,
        "baskets_closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "net": round(sum(x["net"] for x in closed), 2),
        "closes": closed,
        "note": (
            "M15 OHLC reconstruction of published defaults (2-digit scaled). "
            "Not the compiled Market EA; intra-bar ticks would add levels faster. "
            "A bar that adds a level does not also take TP/BE off the other extreme. "
            "The 2024-03 JSON written before that guard understates ruin and is not evidence."
        ),
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in report if k != "closes"}, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
