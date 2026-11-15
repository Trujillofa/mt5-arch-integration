# Feasibility: MT5 MCP gold dump, reverse-engineered into a new edge, run as house autoresearch

**Date:** 2026-10-03
**Proposal reviewed:** use MT5 MCP to fetch as much gold information as possible, reverse-engineer a new gold edge from that fetch, and keep working by this repo's autoresearch workflow until a full research cycle is done.
**Scope of this note:** feasibility only. It selects no rule, grid, parameter set, or profit factor. It does not authorize a charter, a screen, holdout use, or live trading.

NOT_FEASIBLE

The proposal as one package cannot be carried out. Route C cannot return the multi-year develop tape a screen uses. Route B was not called, is chart-cache limited, and already supplied the M1 window behind the newest study, which is closed. Turning either pull into an edge by continued search would skip the freeze and treat holdout-barred selection as a loop. Descriptive inventory of specs and recent bars is the only reading of "reverse engineering" that stays inside the research rules, and that inventory is not an edge.

## What each MT5 MCP route can return

### Route C — `mt5-arch mcp`

Source: `docs/HOWTO-MT5-AI-MCP.md` (Route C) and `src/mt5_arch/mcp_server.py`.

Tools on this server are only `ping`, `account`, `symbols`, `candles`, `config`, `brokers`, and `resolve`. `MAX_CANDLE_COUNT = 500`. `candles` takes `symbol`, `timeframe`, and `count` (default 10, rejected outside 1..500) and calls `copy_rates`, which keeps the tail of the bridge snapshot when the file is longer than `count`. There is no start time, no end time, and no offset, so a second call returns the same tail. The HOWTO states there is no positions or order tool (the EA may write `positions.json`; this server does not expose it) and no `OrderSend`. `config` is a redacted settings summary. `brokers` lists profiles from `config/brokers/*.env` with no market data. `resolve` maps canonical and broker names through `config/symbols/registry.json` and does not open a bridge. `ping`, `account`, `symbols`, and `candles` fail closed when `heartbeat.txt` is older than `MT5_BRIDGE_MAX_AGE`.

Gold names the registry can spell, without a live quote: Vantage `XAUUSD`, FP Markets `XAUUSD.r`, Exness `XAUUSDm` (`config/symbols/registry.json`). Vantage `XAUUSD` is registered with digits 2, contract size 100, point 0.01.

What route C cannot return: a paged history, open positions, deal history, an order path, or more than 500 bars per `candles` call.

### Route B — official HTTP MCP

Source: `docs/HOWTO-MT5-AI-MCP.md` (Route B and "M1 history from official MCP") and the allowlist in `scripts/fetch_m1_official_mcp.py`. This review did not call route B. No route B bars are quoted here.

The fetch client allowlist is `get_chart_history` and `get_time_information`. Any other tool name raises before the request is sent. The URL host must be loopback (`127.0.0.1`, `localhost`, or `::1`) because that server can trade. Only the `terminal64.exe` that bound `127.0.0.1:22346` first answers. The server returns bars already in that terminal's chart cache. Cache length is Charts → Max bars in chart (`[Charts] MaxBars` in the prefix `Config/common.ini`). The HOWTO states that 100000 bars is about three months of M1. It also records that on 2026-09-24 the Vantage prefix cap changed from 100000 to 2000000 and that the new cap applies only after that terminal is started again. This review does not restart the live Vantage terminal and does not edit the Wine prefix. A larger MaxBars still serves chart cache on the terminal that owns the port. It is not a substitute for the offline develop file a screen already pins.

### Live route C probe (2026-10-03)

Capture: implementer scratch `mcp-gold-probe.txt`. Tools called: `ping`, `resolve`, `symbols`. No `candles` call, so the capture has no OHLC.

- `ping` failed closed: `Bridge data is stale (1381033s old). Is the EA running with Algo Trading enabled?`
- `symbols` for `XAUUSD` failed closed: `Bridge data is stale (1381041s old). Is the EA running with Algo Trading enabled?`
- `resolve` of `XAUUSD` on `vantage` returned the registry row only: broker symbol `XAUUSD`, digits 2, contract size 100, point 0.01. That row is not a quote and not a bar.

The live probe failed closed. Nothing in this memo fills that gap with fabricated OHLC or with an older phase0 file presented as a fresh MCP pull.

## Cap versus the tape a screen uses

The develop H1 dump a later XAU screen actually reads is `results/xau_fomc_h4/xauusd_h1_2018_2025.csv`: 45,863 bars, first true H1 2018-04-02 01:00, last bar 2025-12-31 23:00 (`results/xau_fomc_h4/README.md`). Route C's `candles` ceiling is 500 bars (`MAX_CANDLE_COUNT`). 500 bars do not cover 2018-04-02 through 2025-12-31. 500 / 45,863 is about 1.1% of that file, and the tool cannot walk backward to collect the rest.

Holdout start in `results/xau_holdout_lock.json` is `2026-01-01T00:00:00+00:00`, with `develop_end` at 2025-12-31. The same README says holdout remains `2026-01-01`. A 500-bar tail fetched on 2026-10-03 would sit on the live side of that cut. Using it to choose a rule would put holdout prices into selection. The holdout is not used for selection.

The newest study already spent an official-MCP gold pull. See the next section. Another cache pull does not create a new develop tape.

## Standing protocol, and where "keep working" breaks it

Quoted from the first status block of `results/xau_loop_status.md` (2026-09-24), which is the status truth for this memo:

- newest study name: `xau_gold_session_study`
- **next_step:** `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`
- promote / live_go / PAPER_GO: no / false / no
- disposition: `SCREEN_FAIL` — no idea group clears develop — holdout untouched
- tape note in that block: Vantage XAUUSD M1 via official MT5 MCP (`scripts/fetch_m1_official_mcp.py`), develop 500 days 2024-01-02 through 2025-12-31
- multiplicity in that block: **K_prior=25 for the next family**

live_go remaining false is the standing flag. This proposal does not set it otherwise. `docs/research/XAU-FAMILY-PROTOCOL-V2.md` opens on the same idle token with promote=no and live_go=false. `docs/CHARTER-RESEARCH-LAYER.md` withholds live orders unless a person explicitly consents. `AGENTS.md` says never pass `--live` without that consent.

Mismatches between "fetch, reverse-engineer an edge, keep searching until a full cycle" and the house loop:

1. Holdout start `2026-01-01` is never used for selection (`results/xau_holdout_lock.json` rule text; `AGENTS.md` pre-registered holdout). Anything that selects parameters fits strictly before that timestamp.
2. A new `family_id` is frozen before any develop metric. `AGENTS.md` requires the freeze (charter, thesis memo, and a `results/xau_loop_status.md` prepend) to be its own git commit before any develop metric. Screen JSON and MD are a later commit. Freeze and screen do not share a step. `XAU-FAMILY-PROTOCOL-V2.md` repeats the same order: new `family_id`, freeze under `results/xau_charters/` before inspecting the real grid.
3. promote / live_go / PAPER_GO stay no / false / no, matching the status head. This review does not promote.
4. Closed or parked families stay closed. The 2026-08-21 consolidation block in `results/xau_loop_status.md` says do not subset MR signals, invert ANTI, or retune closed books. Protocol paper gates do not revive closed `family_id`s (`XAU-FAMILY-PROTOCOL-V2.md`). The head block's own "do not" list bars retune of the session study and bars running holdout on those three idea groups.

House autoresearch is a pre-registered develop grid plus null calibration against a lock. The specimen `scripts/btc_trend_pullback_autoresearch.py` takes grid, costs, holdout, and the a-priori cell from a lock file, and its header states that holdout never enters a sort key. Unbounded search-until-an-edge on the same tape is incompatible with that protocol. One-line rule: unbounded keep-searching is not a substitute for a pre-registered freeze.

`K_prior` for the next family is 25 from the status head above. Older notes that still say 20 are stale relative to this file.

## Reverse engineering, scoped

In this review, reverse engineering means a descriptive inventory of the tool surface, the symbol registry, and whatever recent bars a read-only call actually returns. It does not mean parameter selection, and it does not mean decompiling `terminal64.exe` or vendor experts.

The inventory from this pass:

- Route C tool list and the 500-bar tail cap, from the server source.
- Registry spelling and Vantage contract pins for `XAUUSD`, from `resolve` (confirmed) and the registry file (FP Markets and Exness spellings, not re-quoted live).
- Live `ping` and `symbols` both down on a stale heartbeat. No fresh gold bars.

That inventory does not name a thesis. The standing next step is still `RESEARCH_IDLE_PENDING_GENUINELY_NEW_THESIS`. This memo does not invent that thesis.

## Prior session study stays closed

`xau_gold_session_study` is the study at the head of `results/xau_loop_status.md`. It is `SCREEN_FAIL`. Its holdout is untouched. It already used official MT5 MCP M1 (route B, read-only allowlist) for a 500-day develop window. This proposal does not re-run it and does not retune it. Kill label on that block: `KILL_XAU_GOLD_SESSION_STUDY`.

## Why the token is NOT_FEASIBLE

- A full research cycle needs a frozen `family_id` and the multi-year develop tape (45,863 H1 bars, 2018-04-02 through 2025-12-31). The MCP path in the proposal does not supply that tape: route C stops at 500 bars with no history cursor, and the live bridge failed closed on 2026-10-03.
- Route B can return only chart-cache history, was not probed, and is the source the closed session study already used. Restarting the live Vantage terminal to enlarge MaxBars or to free port 22346 is outside this review.
- "Keep working until an edge appears" is unbounded search. The house workflow runs one pre-registered grid against a lock, with holdout barred from selection, after a freeze commit of its own. Those are different procedures.
- No new charter, screen, null trial, or paper gate follows from this note.

## Sources

- `docs/HOWTO-MT5-AI-MCP.md` — routes B and C, loopback, MaxBars, no positions tool, no `OrderSend` on route C.
- `src/mt5_arch/mcp_server.py` — `MAX_CANDLE_COUNT = 500`, tool list, `candles` argument check.
- `src/mt5_arch/file_bridge.py` — `copy_rates` tail slice; stale heartbeat fails closed.
- `scripts/fetch_m1_official_mcp.py` — route B allowlist. Not executed for this memo.
- `config/symbols/registry.json` — `XAUUSD` / `XAUUSD.r` / `XAUUSDm`.
- `results/xau_fomc_h4/README.md` — 45,863 H1 bars, 2018-04-02 through 2025-12-31.
- `results/xau_holdout_lock.json` — `holdout_start` `2026-01-01`, holdout never used for selection.
- `results/xau_loop_status.md` — first block, 2026-09-24, `xau_gold_session_study`.
- `docs/research/XAU-FAMILY-PROTOCOL-V2.md` — idle disposition, freeze before the real grid, no revival of closed families.
- `AGENTS.md` — freeze commit before any develop metric; holdout rule; no `--live` without consent.
- `docs/CHARTER-RESEARCH-LAYER.md` — no live orders from research without explicit consent.
- `scripts/btc_trend_pullback_autoresearch.py` — lock-driven autoresearch specimen.
