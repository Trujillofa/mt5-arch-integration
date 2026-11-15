# Is the Renko event clock a new edge? — review, 2026-09-19

**Verdict: no, not on current evidence.** Zero of five pre-registered vehicles clear the
soft gates on the develop window. The family is `SCREEN_FAIL` and the null was not spent.

- Charter: `results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json` (FROZEN 2026-09-19, zero free knobs)
- Thesis memo: `docs/research/XAU-THESIS-renko_event_clock_vendor_v1.md`
- Screen artifacts: `results/xau_renko_event_clock_vendor_screen.{json,md}`
- Sources: `mql5/Experts/vendor/` (MQL5 Code Base 77234 v1.10, 77236 v1.30)
- Holdout: **untouched**. `promote=no`, `live_go=false`.

## What was tested

Two published MQL5 experts build fixed-size Renko internally from bid ticks and trade it —
one with Wilder ADX/DI over the brick series, one with four independent Bollinger engines.
Their author reports PF 3.14 and 4.22 on XAUUSD.

The interesting question was not "do these EAs work" but **whether the sampling clock is what
killed eleven prior families here**. Every dead family in this program sampled XAUUSD on a
time clock. A Renko brick is a price-event sample: it prints when price has moved a fixed
distance, so quiet hours emit nothing and violent hours emit many bricks. If band and trend
rules fail on time bars because the bars mix regimes, they should work better on brick bars.

To make that falsifiable rather than decorative, the charter freezes all five rule sets with
**every parameter copied verbatim from the vendor**. Nothing was tuned, so there was nothing
to overfit — the hypothesis either survives an independent window and cost model or it does not.

## Result

Develop window, M15 2022-05-17 → 2025-12-31 (85,802 bars), Standard STP spread-only costs,
fixed 0.01 lots on a $10,000 balance.

| vehicle | brick | R:R | risk/trade | n | PF | WR | net $ | maxDD | soft gate |
|---|---|---|---|---|---|---|---|---|---|
| ADX/DI trend (77234) | $16 | 1:0.23 | $672 (6.7%) | 123 | 0.84 | 48.0% | −268.88 | 3.62% | FAIL |
| BB breakout (mode 1) | $17 | 1:0.57 | $714 (7.1%) | 121 | 1.07 | 56.2% | +105.64 | 3.81% | FAIL |
| BB re-entry (mode 2) | $30 | 1:0.58 | $1,455 (14.6%) | 28 | 2.40 | 64.3% | +313.00 | 0.97% | FAIL |
| BB midline (mode 3) | $30 | 1:0.29 | $1,035 (10.3%) | 49 | 0.52 | 36.7% | −522.51 | 7.02% | FAIL |
| BB squeeze (mode 4) | $14 | 1:0.84 | $434 (4.3%) | 67 | 1.11 | 56.7% | +109.02 | 3.19% | FAIL |

Soft gates: n ≥ 40, PF > 1.2, net > 0, DD < 15%.

## Four findings that matter more than the table

**1. The advertised TP/SL geometry is decorative.** Across all five vehicles, stops and
targets accounted for **0–0.8%** of exits. Everything else left on the time stop or a signal
flip. A 42-brick stop on a $16 brick is $672 of gold; a 9.5-brick target is $152. Over a
1060-minute hold, price reaches neither. So these are not 1:0.23 risk-reward systems at all —
they are *"enter after a confirmed brick run, hold 18 to 43 hours, exit on the clock"*
systems, and the TP/SL numbers in the inputs panel describe boundaries that almost never
bind. Any read of the vendor's profit factor as evidence about stop placement is misreading
what the number measures.

**2. The vehicle with the vendor's strongest claim is the worst performer here.** The ADX
expert (vendor PF 3.14) produced the largest sample in this screen — 123 trades — and the
worst trend result: PF 0.84, net −$269, 48% win rate. Large sample, negative sign. That is
the most informative single cell in the table.

**3. The vehicle nearest to passing is a path artefact.** BB breakout came closest (PF 1.07).
Under the reversed intrabar path convention it becomes PF 1.20 and clears the gate. The
charter names that flip as a falsifier before the run, because bricks are reconstructed from
M15 OHLC and the traversal order is an assumption we invented, not a fact we measured. A
result that depends on our assumption is not a result.

**4. The one attractive PF is built on 28 trades.** BB re-entry shows PF 2.40 and a 0.97%
drawdown — on 28 trades in 3.6 years, below the pre-registered floor of 40. Thin n is a
`SCREEN_FAIL` by charter, not a waiver, and lowering the floor after seeing the number is
exactly the move this program's protocol exists to block.

Slippage sensitivity (0/5/10/20 points, frozen, report-only) decays monotonically and rescues
nothing. Overnight swap is not modeled at all, and every vehicle holds overnight — so the
reported net profits are **optimistic** by the unmodeled carry.

## Honest limits of this screen

- **We rebuilt bricks from M15 bars, not ticks.** M15 hides intrabar oscillation, so this
  reconstruction under-counts bricks. Under-counting removes trades; it does not manufacture
  them. That makes a negative result informative and a positive result unconfirmable — which
  is why the charter requires a real-tick run before any promotion.
- **The vendor's own window is inside our locked holdout.** They report 2026-05 → 2026-09;
  `results/xau_holdout_lock.json` fixes `holdout_start = 2026-01-01` under "NEVER used for
  selection". Their numbers are recorded in the charter as a claim and were never used to
  choose anything here. They are also not a contradiction of this screen: a four-month
  trending sample and a 3.6-year sample are not measuring the same thing.
- **Fixed lot, not risk-scaled.** This program's usual 1%-risk sizing cannot express these
  rules: a 42-brick stop sizes below the 0.01 minimum lot, so every trade would be skipped.
  Fixed 0.01 lots is the only faithful contract, and it means the ADX vehicle risks 6.7% of a
  $10,000 account per trade — the Bollinger expert's four concurrent modes sum to about 36%.

## Consequence for the dead-line catalog

The charter bound this up front: the four Bollinger vehicles are honestly adjacent to the
dead `bb_rsi` line, so their failure is recorded as **confirmation of `KILL_BB_RSI_LINE`
across clocks**. Bollinger does not reopen on any clock. The ADX vehicle shares no primitive
with a dead line, and it failed on the largest sample in the screen, so ADX/DI on the brick
clock closes too.

The broader finding is the one worth keeping: **resampling did not rescue these rules.** The
event clock was a real question, it is now answered for this vehicle class, and a future
event-clock attempt needs a primitive that is not already on the dead list — not a new
x-axis for one that is.

## What is worth keeping from the exercise

1. `scripts/renko_core.py` — a stdlib-only, tested brick/ADX/Bollinger port. Reusable for any
   future event-clock work, and it runs without numpy or pandas, so it works under plain
   `uv run pytest`.
2. `scripts/25-run-renko-vendor-backtest.sh` — headless tester harness that pins `MODEL=4`
   (real ticks), generates its `.set` directly from the frozen charter, and **refuses a window
   that reaches the holdout**. The `MODEL=1` default in `19-*.sh` would have made any Renko
   tester run meaningless; that trap is now closed for this path.
3. The vendor experts' **execution plumbing**, which is better than their strategies: volume
   normalization against min/max/step, filling-mode derivation from `SYMBOL_FILLING_MODE` and
   `TRADE_EXEMODE`, real `SymbolInfoSessionTrade` windows, a three-strike failure backoff that
   parks until session end, and an execution-uncertain state machine that pauses requests after
   a TIMEOUT or CONNECTION retcode until it reconciles against order history. That is worth
   reading before the next time this repo touches `OrderSend`.

## The one open question, and how to close it cheaply

Does a real tick feed produce a materially different brick series than the M15 reconstruction?
If it does, finding 3 (the path artefact) and the trade counts both change. That is one
command on a machine with a terminal:

```bash
export WINEPREFIX=~/.mt5-vantage
./scripts/25-run-renko-vendor-backtest.sh adx       XAUUSD M15 2022.05.17 2025.12.31
./scripts/25-run-renko-vendor-backtest.sh bollinger XAUUSD M15 2022.05.17 2025.12.31
```

Both run with `AllowLiveTrading=0` and cannot reach the holdout. If the tester's real-tick run
agrees with this screen, the family is closed on two independent data paths. If it disagrees
sharply, the interesting finding is about our M15 reconstruction, not about the strategy —
and that is worth knowing for every future event-clock idea.
