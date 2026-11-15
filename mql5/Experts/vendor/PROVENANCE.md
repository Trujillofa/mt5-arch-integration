# Vendored MQL5 experts — provenance

Third-party sources kept **verbatim** for provenance and Strategy Tester use.
Do not edit these files. Fixes or variants belong in a separate file that states
what it changed and why.

Downloaded 2026-09-19 from the MQL5 Code Base (freeware section).

| File | Code ID | Version | Author | sha256 |
|---|---|---|---|---|
| `GDS_Renko_ADX_Demo.mq5` | [77234](https://www.mql5.com/en/code/77234) | 1.10 | Andrey Goida (gavaav) | `851979c965c5f97f9449a0d463e0341818c6dcef2982d84271752b44756296ed` |
| `GDS_Renko_Bollinger_4Mode_Demo.mq5` | [77236](https://www.mql5.com/en/code/77236) | 1.30 | Andrey Goida (gavaav) | `0e53dbb7af1b1234b2089fe85baff537cd4f8c855117fa6c675bc071901cf1cd` |

Both carry `#property copyright "Golden Delta"` and link `https://goldendeltaea.com/`.
They are published as educational "Demo" experts by a vendor that also sells a commercial
product. The copyright headers stay intact.

## What they are

Self-contained MT5 experts with no includes, no DLLs, no custom symbols and no offline
charts. Each builds fixed-size Renko internally from the incoming **bid tick** stream
(`OnTick` → `CRenkoBuilder::PushPrice`), two-brick reversal, price quantized to integer
tick units.

- **77234** — Wilder ADX/+DI/−DI computed over completed bricks only. Entry needs
  `ADX ≥ 8.5`, `|+DI − −DI| ≥ 2.5`, brick direction agreeing with DI, and a run of ≥ 3
  bricks. Exit on raw DI flip (the ADX gate is deliberately not applied to exits), virtual
  TP 9.5 bricks, virtual SL 42 bricks, 1060-minute time stop.
- **77236** — four independent engines, each with its own Renko builder, brick size, band
  parameters, TP/SL/hold/cooldown and magic (`Base+1..Base+4`): Breakout, Re-entry,
  Midline cross, Squeeze breakout. Bands are evaluated before the new close is appended, so
  the evaluated brick never contributes to its own band. Population stdev.

## Safety notes — read before attaching either to a chart

1. **TP and SL are virtual.** Nothing is registered at the broker. If the terminal or the
   EA stops, the position is unprotected. This repo runs MT5 under Wine, where terminal
   death is a documented failure mode (`docs/` on ghost windows and IPC timeouts).
2. **Stop size.** On XAUUSD (`point_size` 0.01, contract 100) the ADX vehicle's 42-brick
   stop is `42 × 16.0 = 672.0` of price. At the minimum 0.01 lot that is **$672 of risk on
   one trade** — 6.7% of a $10,000 account. The Bollinger expert's four modes run
   concurrently and sum to roughly **36%** of a $10,000 account at minimum lot.
3. **The published results sit inside this program's locked holdout.** The vendor reports
   2026-05 .. 2026-09; `results/xau_holdout_lock.json` fixes `holdout_start = 2026-01-01`
   under the rule "NEVER used for selection". Those numbers are a claim, not evidence.
4. **Tick model.** Renko built from ticks is meaningless under the tester's 1-minute OHLC
   model. Any Strategy Tester run must use `MODEL=4` (every tick based on real ticks) —
   `scripts/19-run-htf-fib-backtest.sh` defaults to `MODEL=1`.

No script in this repository deploys these to a live chart.
`scripts/18-install-forex-indicator.sh` copies them into the Wine prefix so MetaEditor can
compile them for the Strategy Tester; attaching them anywhere is a manual act.

## Offline replication

`scripts/renko_core.py` is an independent, stdlib-only Python port of the brick builder and
both indicator stacks, used by `scripts/renko_event_clock_screen.py` to screen the frozen
parameter sets on this program's develop window under the locked cost model. The port
targets behavioural parity with the sources above; `tests/test_renko_core.py` pins the
contract.
