# XAU thesis memo — `renko_event_clock_vendor` v1

**Frozen:** 2026-09-19 · **Charter:** `results/xau_charters/2026-09-19_renko_event_clock_vendor_v1.json`
**Status at freeze:** no develop metric for this family has been computed or inspected.

## The question

Eleven families are dead in this program. Every one of them sampled XAUUSD on a **time**
clock — H1 or M15 bars, session hours, calendar days. `bb_rsi` and `Donchian` are on that
list, so band and breakout *rules* are dead on the time clock.

What has never been tested here is whether the failure belongs to the rules or to the
**clock**. A fixed-size Renko brick is a price-event sample: a brick prints when price has
moved a fixed distance, regardless of how long that took. Quiet hours emit nothing; violent
hours emit many bricks. That is the standard argument for information-driven sampling — the
sampled series has more stable variance per observation than a time-sampled one, so
indicators computed on it are not being fed a mixture of regimes.

If that argument is worth anything on XAUUSD, it should show up as: rules that fail on time
bars work on brick bars. If it is worth nothing, this family closes the question.

## Why the vendor parameters, verbatim

Two MQL5 Code Base experts (77234, 77236) implement exactly this and publish strong results
on XAUUSD — PF 3.14 and PF 4.22. Copying their numbers verbatim, with no grid and no
refinement, buys a real property: **there is nothing for this program to overfit**. The
hypothesis is not "some Renko rule works", which is unfalsifiable; it is "*these five
published rule sets* carry edge on our develop window after our costs", which fails cleanly.

It also inverts the usual burden. A vendor result that survives an independent window on an
independent cost model is worth something. A vendor result that evaporates is worth knowing
before anyone attaches the EA to a chart.

## What would make this true

Every vehicle is a trend or band-continuation rule on the brick series. They pay spread on
entry and they hold overnight. For any of them to clear the soft gates on develop
(n ≥ 40, PF > 1.2, net > 0, DD < 15%), brick-to-brick direction must be **autocorrelated
beyond the two-brick reversal that the construction already imposes**. That is the entire
economic content. The Renko construction guarantees runs of same-direction bricks in a
trend; the question is whether those runs are long enough, often enough, to pay for the
reversals.

## Falsifiers, named before the run

1. **Thin n.** Fewer than 40 develop trades on a vehicle is SCREEN_FAIL, not a waiver.
   A $16 brick on gold prints roughly 900 bricks a year; with a 3-brick entry run and a
   6-brick cooldown, the ADX vehicle may simply not trade enough to be measurable. If so,
   that is the answer: the vehicle is unmeasurable on this data, not promising.
2. **Path artefact.** We rebuild bricks from M15 OHLC, not ticks. The screen runs both
   intrabar path conventions. If the verdict or the sign of net profit flips between them,
   the result is an artefact of an assumption we invented, and the family fails.
3. **Stop geometry.** The ADX vehicle risks 42 bricks to make 9.5 — an R:R of 1:0.23.
   A rule with that shape is profitable only at a very high hit rate, and a high hit rate in
   a four-month sample is exactly what a rarely-touched stop looks like. If develop shows
   the stop being reached at a normal rate, the vendor's profit factor is explained and gone.
4. **Cost slope.** Slippage sensitivity runs at 0/5/10/20 points, frozen, report-only.
   A vehicle whose edge dies by 5 points was never an edge.
5. **Unmodeled carry.** These rules hold 18–43 hours. The bar simulator does not model swap,
   so every net profit reported here is optimistic by the carry. A marginal pass is a fail.

## What a pass would and would not license

A pass licenses exactly one next step: a real-tick MT5 Strategy Tester run (`MODEL=4`) on
the same develop window, to check whether the M15 reconstruction was faithful. It licenses
no paper trading, no promotion, and no holdout evaluation. The holdout is untouched by this
family, and the vendor's own reported window sits inside it — which is why the vendor's
numbers are recorded in the charter as a claim and never as evidence.

## Adjacency to dead lines

`bb_rsi` is the nearest dead line and the four Bollinger vehicles are honestly adjacent to
it. The charter binds the consequence up front: if they fail, that is recorded as
confirmation of `KILL_BB_RSI_LINE` **across clocks**, and Bollinger may never be reopened on
any clock. Renaming a dead rule by changing its x-axis is the failure mode this program
exists to prevent, so the cost of trying it is that a failure closes the question
permanently rather than leaving it ajar.
