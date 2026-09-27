#!/usr/bin/env python3
"""Develop-window screen for the frozen ``renko_event_clock_vendor`` family.

Charter: ``results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json``.
Costs:   ``results/xau_research_costs.json`` (Standard STP, spread-only).
Window:  ``time < holdout_start`` from ``results/xau_holdout_lock.json``.

Scores the five pre-registered vehicles independently. Every parameter comes from
the charter; this script has no defaults of its own to tune and refuses to run if
the charter's sha256 no longer matches its sidecar.

Usage::

    python3 scripts/renko_event_clock_screen.py              # screen, write artifacts
    python3 scripts/renko_event_clock_screen.py --dry-run    # print, write nothing

SAFETY: offline research only. Reads the CSV, writes two report files. No orders.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from renko_core import (  # noqa: E402
    BollingerMode,
    Brick,
    RenkoADX,
    RenkoBollinger,
    RenkoBuilder,
    RenkoOverflowError,
    bar_path,
    size_in_tick_units,
)

ROOT = Path(__file__).resolve().parents[1]
CHARTER = ROOT / "results" / "xau_charters" / "2026-09-19_renko_event_clock_vendor_v1.json"
HOLDOUT_LOCK = ROOT / "results" / "xau_holdout_lock.json"
COSTS = ROOT / "results" / "xau_research_costs.json"
DATA = ROOT / "xauusd_data.csv"
OUT_JSON = ROOT / "results" / "xau_renko_event_clock_vendor_screen.json"
OUT_MD = ROOT / "results" / "xau_renko_event_clock_vendor_screen.md"

CONTRACT_SIZE = 100.0
START_BALANCE = 10000.0
TICK_SIZE = 0.01


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_charter() -> dict[str, Any]:
    charter = json.loads(CHARTER.read_text(encoding="utf-8"))
    sidecar = CHARTER.with_suffix(".json.sha256")
    if sidecar.exists():
        expected = sidecar.read_text(encoding="utf-8").strip()
        actual = sha256_of(CHARTER)
        if expected != actual:
            raise SystemExit(
                f"charter sha256 mismatch: sidecar {expected}, file {actual}. "
                "A frozen charter must not be edited; cut a new version instead."
            )
    if charter.get("status") != "FROZEN":
        raise SystemExit(f"charter status is {charter.get('status')!r}, expected FROZEN")
    return charter


@dataclass(frozen=True, slots=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    spread_pts: float


def load_bars(timeframe: str, holdout_start: datetime) -> list[Bar]:
    """Develop-window M15 bars, ascending. Warmup is taken from inside the window."""
    bars: list[Bar] = []
    with DATA.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["timeframe"] != timeframe:
                continue
            ts = datetime.fromisoformat(row["time"])
            if ts >= holdout_start:
                continue
            bars.append(
                Bar(
                    time=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    spread_pts=float(row["spread"]),
                )
            )
    bars.sort(key=lambda b: b.time)
    return bars


# --------------------------------------------------------------------------
# vehicles
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Vehicle:
    key: str
    label: str
    engine: str  # "adx" | "bb"
    brick_size: float
    tp_bricks: float
    sl_bricks: float
    max_hold_minutes: int
    cooldown_bricks: int
    entry_run: int
    max_spread_fraction: float = 0.35
    # adx
    adx_period: int = 14
    adx_threshold: float = 0.0
    min_di_separation: float = 0.0
    # bb
    bb_mode: BollingerMode = BollingerMode.BREAKOUT
    bb_period: int = 20
    deviation: float = 1.0
    squeeze_max_width: float = 1.0e9


def vehicles_from_charter(charter: dict[str, Any]) -> list[Vehicle]:
    r = charter["rule"]
    a = r["vehicle_adx"]
    out = [
        Vehicle(
            key="adx",
            label="ADX/DI trend (77234)",
            engine="adx",
            brick_size=a["brick_size"],
            tp_bricks=a["tp_bricks"],
            sl_bricks=a["sl_bricks"],
            max_hold_minutes=a["max_hold_minutes"],
            cooldown_bricks=a["cooldown_bricks"],
            entry_run=a["entry_run_bricks"],
            max_spread_fraction=a["max_spread_fraction"],
            adx_period=a["adx_period"],
            adx_threshold=a["adx_threshold"],
            min_di_separation=a["min_di_separation"],
        )
    ]
    bb_specs = [
        ("bb_breakout", "BB breakout (77236 mode 1)", "vehicle_bb_breakout", BollingerMode.BREAKOUT),
        ("bb_reentry", "BB re-entry (77236 mode 2)", "vehicle_bb_reentry", BollingerMode.REENTRY),
        ("bb_midline", "BB midline cross (77236 mode 3)", "vehicle_bb_midline", BollingerMode.MIDLINE_CROSS),
        ("bb_squeeze", "BB squeeze (77236 mode 4)", "vehicle_bb_squeeze", BollingerMode.SQUEEZE_BREAKOUT),
    ]
    for key, label, charter_key, mode in bb_specs:
        v = r[charter_key]
        out.append(
            Vehicle(
                key=key,
                label=label,
                engine="bb",
                brick_size=v["brick_size"],
                tp_bricks=v["tp_bricks"],
                sl_bricks=v["sl_bricks"],
                max_hold_minutes=v["max_hold_minutes"],
                cooldown_bricks=v["cooldown_bricks"],
                entry_run=v["entry_run_bricks"],
                bb_mode=mode,
                bb_period=v["bb_period"],
                deviation=v["deviation"],
                squeeze_max_width=v.get("squeeze_max_width_bricks", 1.0e9),
            )
        )
    return out


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------


@dataclass
class Trade:
    direction: int
    entry_time: datetime
    entry_px: float
    cost: float
    exit_time: datetime | None = None
    exit_px: float | None = None
    reason: str = ""
    pnl: float = 0.0


@dataclass
class Stats:
    bricks: int = 0
    trades: list[Trade] = field(default_factory=list)
    overflow: bool = False
    exit_reasons: dict[str, int] = field(default_factory=dict)


def simulate(
    bars: list[Bar],
    vehicle: Vehicle,
    *,
    convention: str,
    slippage_points: float,
    commission_per_lot: float,
    point_size: float,
    lots: float,
) -> Stats:
    """Replay one vehicle over the bars on the assumed intrabar path.

    Ordering mirrors the vendor ``OnTick``: virtual stop/target are evaluated
    against the incoming price *before* that price is pushed into the brick
    builder, so a stop reached mid-bar wins over a brick that the same bar
    completes later on its path.
    """
    stats = Stats()
    builder = RenkoBuilder(TICK_SIZE, size_in_tick_units(vehicle.brick_size, TICK_SIZE))
    brick_size = builder.brick_size
    adx = RenkoADX(vehicle.adx_period) if vehicle.engine == "adx" else None
    bb = RenkoBollinger(vehicle.bb_period) if vehicle.engine == "bb" else None

    tp_dist = vehicle.tp_bricks * brick_size
    sl_dist = vehicle.sl_bricks * brick_size
    spread_gate_price = vehicle.max_spread_fraction * brick_size

    open_trade: Trade | None = None
    cooldown = 0
    entry_bar_index = -1

    def close_trade(trade: Trade, when: datetime, px: float, reason: str) -> None:
        nonlocal open_trade, cooldown
        trade.exit_time = when
        trade.exit_px = px
        trade.reason = reason
        trade.pnl = (px - trade.entry_px) * CONTRACT_SIZE * lots * trade.direction - trade.cost
        stats.trades.append(trade)
        stats.exit_reasons[reason] = stats.exit_reasons.get(reason, 0) + 1
        open_trade = None
        cooldown = vehicle.cooldown_bricks

    for i, bar in enumerate(bars):
        for price in bar_path(bar.open, bar.high, bar.low, bar.close, convention):
            # 1. virtual stop / target against the incoming price
            if open_trade is not None:
                d = open_trade.direction
                move = d * (price - open_trade.entry_px)
                if move <= -sl_dist:
                    close_trade(open_trade, bar.time, open_trade.entry_px - d * sl_dist, "SL")
                elif move >= tp_dist:
                    close_trade(open_trade, bar.time, open_trade.entry_px + d * tp_dist, "TP")

            # 2. feed the event clock
            try:
                new_bricks: list[Brick] = builder.push_price(price)
            except RenkoOverflowError:
                stats.overflow = True
                return stats
            if not new_bricks:
                continue
            stats.bricks += len(new_bricks)

            signal = 0
            raw = 0
            for brick in new_bricks:
                if adx is not None:
                    adx.push(brick)
                    raw = adx.raw_direction()
                    gated = adx.direction(vehicle.adx_threshold, vehicle.min_di_separation)
                    signal = (
                        gated
                        if gated != 0 and brick.direction == gated and brick.run >= vehicle.entry_run
                        else 0
                    )
                else:
                    assert bb is not None
                    raw = bb.push(
                        brick, vehicle.bb_mode, vehicle.deviation, brick_size, vehicle.squeeze_max_width
                    )
                    signal = (
                        raw if raw != 0 and brick.run >= vehicle.entry_run and brick.direction == raw else 0
                    )
                last_close = brick.close

            if cooldown > 0:
                cooldown = max(0, cooldown - len(new_bricks))

            # 3. signal exit on the completed brick
            if open_trade is not None:
                d = open_trade.direction
                if bb is not None and vehicle.bb_mode == BollingerMode.REENTRY and bb.ready:
                    # mode 2 banks at the midline rather than waiting for a flip
                    if (d > 0 and last_close >= bb.mid) or (d < 0 and last_close <= bb.mid):
                        close_trade(open_trade, bar.time, last_close, "BB_MID")
                elif raw != 0 and raw == -d:
                    close_trade(open_trade, bar.time, last_close, "SIGNAL_FLIP")
                continue

            # 4. entry
            if cooldown > 0 or signal == 0:
                continue
            if bar.spread_pts * point_size > spread_gate_price:
                continue
            cost = (
                (bar.spread_pts + 2.0 * slippage_points) * point_size * CONTRACT_SIZE * lots
                + 2.0 * commission_per_lot * lots
            )
            open_trade = Trade(direction=signal, entry_time=bar.time, entry_px=last_close, cost=cost)
            entry_bar_index = i

        # max hold is a wall-clock rule, checked once a bar like the vendor's time exit
        if open_trade is not None and vehicle.max_hold_minutes > 0:
            held = (bar.time - open_trade.entry_time).total_seconds() / 60.0
            if held >= vehicle.max_hold_minutes:
                close_trade(open_trade, bar.time, bar.close, "TIME")

    if open_trade is not None and bars:
        close_trade(open_trade, bars[-1].time, bars[-1].close, "EOD_FORCE")
    _ = entry_bar_index
    return stats


def metrics(stats: Stats) -> dict[str, Any]:
    trades = stats.trades
    n = len(trades)
    if n == 0:
        return {
            "n_trades": 0,
            "net_profit": 0.0,
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_pnl": 0.0,
            "bricks": stats.bricks,
            "exit_reasons": stats.exit_reasons,
            "overflow": stats.overflow,
        }
    wins = [t.pnl for t in trades if t.pnl > 0.0]
    losses = [t.pnl for t in trades if t.pnl <= 0.0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    equity = START_BALANCE
    peak = START_BALANCE
    max_dd = 0.0
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        if peak > 0.0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return {
        "n_trades": n,
        "net_profit": round(sum(t.pnl for t in trades), 2),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0.0 else float("inf"),
        "win_rate_pct": round(100.0 * len(wins) / n, 2),
        "max_drawdown_pct": round(100.0 * max_dd, 2),
        "avg_pnl": round(sum(t.pnl for t in trades) / n, 2),
        "bricks": stats.bricks,
        "exit_reasons": dict(sorted(stats.exit_reasons.items())),
        "overflow": stats.overflow,
    }


def soft_gate_verdict(m: dict[str, Any], gates: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if m["n_trades"] < gates["n_trades_min"]:
        reasons.append(f"n_trades {m['n_trades']} < {gates['n_trades_min']}")
    if m["profit_factor"] < gates["profit_factor_min"]:
        reasons.append(f"PF {m['profit_factor']} < {gates['profit_factor_min']}")
    if m["net_profit"] <= gates["net_profit_gt"]:
        reasons.append(f"net {m['net_profit']} <= {gates['net_profit_gt']}")
    if m["max_drawdown_pct"] > gates["max_drawdown_pct_max"]:
        reasons.append(f"DD {m['max_drawdown_pct']}% > {gates['max_drawdown_pct_max']}%")
    return (not reasons), reasons


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the summary, write no artifacts")
    args = ap.parse_args(argv)

    charter = load_charter()
    lock = json.loads(HOLDOUT_LOCK.read_text(encoding="utf-8"))
    costs = json.loads(COSTS.read_text(encoding="utf-8"))

    costs_sha = sha256_of(COSTS)
    expected_costs_sha = charter["fixed"]["costs"]["costs_document_sha256"]
    if costs_sha != expected_costs_sha:
        raise SystemExit(
            f"cost document changed since freeze: charter {expected_costs_sha}, file {costs_sha}"
        )

    holdout_start = datetime.fromisoformat(lock["holdout_start"])
    timeframe = charter["instrument"]["timeframe"]
    bars = load_bars(timeframe, holdout_start)
    if not bars:
        raise SystemExit(f"no {timeframe} bars before {holdout_start.isoformat()} in {DATA}")

    point_size = costs["point_size"]
    commission = costs["commission_per_lot"]
    lots = charter["fixed"]["lots"]
    gates = charter["gates"]["soft"]
    slippage_grid = charter["success"]["slippage_sensitivity"]["points"]
    base_slippage = costs["slippage_points"]

    vehicles = vehicles_from_charter(charter)

    report: dict[str, Any] = {
        "family_id": charter["family_id"],
        "charter": str(CHARTER.relative_to(ROOT)),
        "charter_sha256": sha256_of(CHARTER),
        "data_csv_sha256": sha256_of(DATA),
        "costs_sha256": costs_sha,
        "cost_label": costs["cost_label"],
        "window": {
            "rule": "time < holdout_start",
            "holdout_start": lock["holdout_start"],
            "timeframe": timeframe,
            "bars": len(bars),
            "first_bar": bars[0].time.isoformat(),
            "last_bar": bars[-1].time.isoformat(),
        },
        "sizing": {"lots": lots, "contract_size": CONTRACT_SIZE, "start_balance": START_BALANCE},
        "gates_soft": gates,
        "holdout_touched": False,
        "vehicles": {},
    }

    for v in vehicles:
        base = simulate(
            bars,
            v,
            convention="ohlc_tester_default",
            slippage_points=base_slippage,
            commission_per_lot=commission,
            point_size=point_size,
            lots=lots,
        )
        base_m = metrics(base)
        passed, reasons = soft_gate_verdict(base_m, gates)

        slippage_rows = {}
        for slip in slippage_grid:
            s = simulate(
                bars,
                v,
                convention="ohlc_tester_default",
                slippage_points=float(slip),
                commission_per_lot=commission,
                point_size=point_size,
                lots=lots,
            )
            sm = metrics(s)
            slippage_rows[str(slip)] = {
                "net_profit": sm["net_profit"],
                "profit_factor": sm["profit_factor"],
                "n_trades": sm["n_trades"],
            }

        alt = simulate(
            bars,
            v,
            convention="reversed",
            slippage_points=base_slippage,
            commission_per_lot=commission,
            point_size=point_size,
            lots=lots,
        )
        alt_m = metrics(alt)
        alt_passed, _ = soft_gate_verdict(alt_m, gates)

        def sign(x: float) -> int:
            return (x > 0) - (x < 0)

        path_flip = (sign(base_m["net_profit"]) != sign(alt_m["net_profit"])) or (passed != alt_passed)

        risk_per_trade = v.sl_bricks * v.brick_size * CONTRACT_SIZE * lots
        report["vehicles"][v.key] = {
            "label": v.label,
            "brick_size": v.brick_size,
            "tp_bricks": v.tp_bricks,
            "sl_bricks": v.sl_bricks,
            "risk_per_trade_usd": round(risk_per_trade, 2),
            "risk_per_trade_pct_of_start_balance": round(100.0 * risk_per_trade / START_BALANCE, 2),
            "reward_risk": round(v.tp_bricks / v.sl_bricks, 3),
            "base": base_m,
            "soft_gate_pass": passed,
            "soft_gate_failures": reasons,
            "slippage_sensitivity": slippage_rows,
            "path_reversed": alt_m,
            "path_verdict_flip": path_flip,
        }

    passers = [k for k, r in report["vehicles"].items() if r["soft_gate_pass"] and not r["path_verdict_flip"]]
    report["n_passers"] = len(passers)
    report["passers"] = passers
    report["disposition"] = "SCREEN_FAIL" if not passers else "SCREEN_PASS_PENDING_NULL"
    report["null_spent"] = False
    report["promote"] = False
    report["live_go"] = False

    text = render_markdown(report)
    print(text)
    if not args.dry_run:
        OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(text, encoding="utf-8")
        print(f"\nwrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    return 0


def render_markdown(report: dict[str, Any]) -> str:
    w = report["window"]
    lines = [
        f"# `{report['family_id']}` — develop screen",
        "",
        f"**Charter:** `{report['charter']}` · sha `{report['charter_sha256'][:16]}`",
        f"**Window:** {w['timeframe']} {w['first_bar'][:10]} → {w['last_bar'][:10]} "
        f"({w['bars']:,} bars, `time < {w['holdout_start'][:10]}`) · holdout untouched",
        f"**Costs:** `{report['cost_label']}` · fixed {report['sizing']['lots']} lots · "
        f"start balance ${report['sizing']['start_balance']:,.0f}",
        f"**Disposition:** **{report['disposition']}** · passers {report['n_passers']}/5 · "
        f"promote no · live_go false",
        "",
        "## Per-vehicle result (base path convention, base slippage)",
        "",
        "| vehicle | brick | R:R | risk/trade | n | PF | WR | net $ | maxDD | soft gate |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _key, r in report["vehicles"].items():
        b = r["base"]
        pf = "inf" if b["profit_factor"] == float("inf") else f"{b['profit_factor']:.2f}"
        verdict = "**PASS**" if r["soft_gate_pass"] else "FAIL"
        lines.append(
            f"| {r['label']} | ${r['brick_size']:.0f} | 1:{r['reward_risk']:.2f} | "
            f"${r['risk_per_trade_usd']:,.0f} ({r['risk_per_trade_pct_of_start_balance']:.1f}%) | "
            f"{b['n_trades']} | {pf} | {b['win_rate_pct']:.1f}% | {b['net_profit']:,.2f} | "
            f"{b['max_drawdown_pct']:.2f}% | {verdict} |"
        )
    lines += ["", "## Gate failures", ""]
    for _key, r in report["vehicles"].items():
        if r["soft_gate_failures"]:
            lines.append(f"- **{r['label']}** — " + "; ".join(r["soft_gate_failures"]))
        else:
            lines.append(f"- **{r['label']}** — clears the soft gates")
    lines += ["", "## Slippage sensitivity (frozen, report-only)", "", "| vehicle | " +
              " | ".join(f"{p} pt" for p in next(iter(report["vehicles"].values()))["slippage_sensitivity"]) +
              " |", "|---|" + "---|" * len(next(iter(report["vehicles"].values()))["slippage_sensitivity"])]
    for _key, r in report["vehicles"].items():
        cells = [f"{row['net_profit']:,.0f}" for row in r["slippage_sensitivity"].values()]
        lines.append(f"| {r['label']} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Path-convention falsifier",
        "",
        "Bricks are rebuilt from M15 OHLC, so the intrabar path is assumed. A verdict or "
        "net-profit sign that flips between conventions is an artefact of that assumption.",
        "",
        "| vehicle | base net $ | base PF | reversed net $ | reversed PF | flip |",
        "|---|---|---|---|---|---|",
    ]
    for _key, r in report["vehicles"].items():
        bpf = "inf" if r["base"]["profit_factor"] == float("inf") else f"{r['base']['profit_factor']:.2f}"
        apf = (
            "inf"
            if r["path_reversed"]["profit_factor"] == float("inf")
            else f"{r['path_reversed']['profit_factor']:.2f}"
        )
        lines.append(
            f"| {r['label']} | {r['base']['net_profit']:,.2f} | {bpf} | "
            f"{r['path_reversed']['net_profit']:,.2f} | {apf} | "
            f"{'**YES**' if r['path_verdict_flip'] else 'no'} |"
        )
    lines += [
        "",
        "## Exit mix — where the advertised TP/SL geometry actually goes",
        "",
        "| vehicle | exits | TP+SL share |",
        "|---|---|---|",
    ]
    for _key, r in report["vehicles"].items():
        reasons = r["base"]["exit_reasons"]
        mix = ", ".join(f"{k} {v}" for k, v in reasons.items()) or "—"
        n = max(1, r["base"]["n_trades"])
        share = 100.0 * (reasons.get("TP", 0) + reasons.get("SL", 0)) / n
        lines.append(f"| {r['label']} | {mix} | {share:.1f}% |")
    lines += ["", "_Offline research artifact. No orders. Holdout not evaluated._", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
