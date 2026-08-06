# X.com research notes for XAU design (2026-08-06)

**Purpose:** External ideas to inform *develop-only* optimization of existing lanes. Not signals to trade live. Not financial advice.

## Themes extracted (actionable for H1 systems)

### 1. Higher-timeframe direction first
- Multiple accounts stress Daily/H4 trend, then only trade *with* the trend (continuation / buy-on-pullback in bullish structure).
- **Lane mapping:** `donchian_turtle`, `atr_trail_breakout`, `htf_fib` — add H4 EMA200 / H4 close>EMA bias as hard filter; forbid counter-trend entries.

### 2. Pullback-to-zone, not chase breakouts
- Dominant retail framing on X: wait for retrace into support / FVG / prior RBS after breakout; avoid FOMO entries at extremes.
- **Lane mapping:** `vol_gate_sparse` already mean-rev; strengthen with *post-breakout retest* variant. New sibling: `htf_pullback` = H4 up + H1 touch ema20/50 or prior swing demand + RSI not overbought.

### 3. Risk rules (portable)
- Risk ~1% per trade; max 1–2 trades/day; move SL to break-even after first target.
- **Lane mapping:** all simulators — optional `be_at_r: 1.0` (move SL to entry after +1R); `max_entries_per_day: 2`; cooldown tied to calendar day not just bars.

### 4. Volatility / regime awareness
- Donchian community: range expansion vs compression; rejection of failed breakouts → mean reversion.
- Turtle classic: size by ATR “N”; risk fixed fraction of equity.
- **Lane mapping:** keep `atr_pctile` gates; add *failed-breakout fade* as optional mode only in low atr_pctile; trail sizing stays ATR-based.

### 5. Structure / extremes
- Trade “extremes” (range high/low, weekly levels) rather than mid-range noise.
- **Lane mapping:** donchian entry only if close outside prior channel *and* distance from mid channel > k*ATR.

### 6. What we deliberately ignore
- Specific call levels (4275 sell, 4240 buy, etc.) — not backtestable rulesets without cherry-picking.
- Signal-service marketing posts without structural rules.
- Intraday M5 FVG entries unless we build M5 data (out of current H1 pipeline scope for this run).

## Prior quantitative status (do not discard without deep opt)

| Lane | Last holdout signal | Why keep optimizing |
|------|---------------------|---------------------|
| vol_gate_sparse | PF~1.54 WR~65 DD~2 n=17 | Closest to gates; need **more trades** not abandon |
| donchian_turtle | PF>1.3 n≥20 NP strong, WR low | Gate mismatch (WR); optimize expectancy/trail/partial/BE |
| atr_trail_breakout | weak late holdout | Add HTF bias + BE + session filter before discard |
| htf_fib | broken stamp / few trades | **Fix confirmation lag** then full param opt on develop |

## Optimization doctrine for next workflow

1. **Never discard a lane until develop budget exhausted** (local + neighborhood + structure variants).
2. Optimize **only on develop** (`time < 2026-01-01`); holdout sealed until shortlist frozen.
3. Lane-specific promote scores on develop:
   - vol_gate: maximize `min(n_trades,40)` subject to PF>1.3, WR>55, DD<8
   - turtle/trail: maximize expectancy * sqrt(n) with PF>1.3, DD<12 (WR secondary)
   - fib: after bugfix, require n≥15 develop and PF>1.2 before any holdout look
4. Final sealed holdout once per shortlisted champion (1 per lane + optional hybrids).
